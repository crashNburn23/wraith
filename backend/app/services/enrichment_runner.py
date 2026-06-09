import asyncio
import logging
import re
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import Article, IOC, TTPTag, ThreatActor, ArticleActor, CVEMention, IOCWhitelist
from app.services.enrichment_prompt import enrich_article
from app.services import job_state
from app.core.config import settings

# Module-level whitelist cache — loaded at the start of each batch run
_whitelist: set[str] = set()

logger = logging.getLogger(__name__)

# ─── IOC validation ───────────────────────────────────────────────────────────

_VALID_IOC_TYPES = {"ip", "domain", "hash", "url", "email"}

_IPV4_RE  = re.compile(r"^\d{1,3}(?:[.\[\]]\d{1,3}){3}$")
_IPV6_RE  = re.compile(r"^[0-9a-fA-F:]{7,39}$")
_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9\[\]]([a-zA-Z0-9\-\[\]]{0,61}[a-zA-Z0-9\[\]])?(\.[a-zA-Z0-9\[\]\-]+)+$")
_MD5_RE   = re.compile(r"^[0-9a-fA-F]{32}$")
_SHA1_RE  = re.compile(r"^[0-9a-fA-F]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_URL_RE   = re.compile(r"^https?://", re.IGNORECASE)
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")

# Well-known legitimate domains that should never be treated as malicious IOCs
_BENIGN_DOMAINS = {
    # Security vendors / research
    "github.com", "virustotal.com", "shodan.io", "any.run", "hybrid-analysis.com",
    "urlscan.io", "abuse.ch", "app.any.run", "tria.ge", "bazaar.abuse.ch",
    "malwarebazaar.abuse.ch", "threatfox.abuse.ch", "feodotracker.abuse.ch",
    "proofpoint.com", "safebreach.com", "crowdstrike.com", "mandiant.com",
    "recordedfuture.com", "team-cymru.com", "shadowserver.org",
    "talosintelligence.com", "talos.com", "unit42.paloaltonetworks.com",
    "paloaltonetworks.com", "checkpoint.com", "sentinelone.com",
    "secureworks.com", "fireeye.com", "huntress.com",
    # Cloud/infra
    "amazonaws.com", "azure.com", "cloudflare.com", "fastly.com",
    "akamai.com", "digitalocean.com", "linode.com",
    # Microsoft / Apple / Google / Amazon
    "microsoft.com", "windows.com", "office.com", "live.com",
    "google.com", "googleapis.com", "gstatic.com", "youtube.com",
    "apple.com", "icloud.com", "amazon.com", "aws.amazon.com",
    # Government / standards
    "cisa.gov", "nist.gov", "nvd.nist.gov", "us-cert.gov", "cve.org",
    "mitre.org", "attack.mitre.org",
    # News / reference
    "exploit-db.com", "bleepingcomputer.com", "theregister.com",
    "techcrunch.com", "wired.com", "darkreading.com", "securityweek.com",
    "bbc.co.uk", "reuters.com", "krebsonsecurity.com", "arstechnica.com",
    # Test/generic
    "example.com", "test.com", "localhost",
}


def _is_benign_domain(hostname: str) -> bool:
    h = hostname.lower().replace("[", "").replace("]", "")
    return h in _BENIGN_DOMAINS or any(
        h == d or h.endswith("." + d) for d in _BENIGN_DOMAINS
    )


def _validate_ioc(ioc_type: str, value: str) -> bool:
    if ioc_type not in _VALID_IOC_TYPES:
        return False
    v = value.strip()
    if not v or v.lower() == "null" or len(v) > 512:
        return False
    # reject anything with spaces (except URLs which may have none in practice)
    if " " in v and ioc_type != "url":
        return False
    if ioc_type == "ip":
        return bool(_IPV4_RE.match(v) or _IPV6_RE.match(v))
    if ioc_type == "domain":
        if _is_benign_domain(v):
            return False
        return bool(_DOMAIN_RE.match(v))
    if ioc_type == "hash":
        return bool(_MD5_RE.match(v) or _SHA1_RE.match(v) or _SHA256_RE.match(v))
    if ioc_type == "url":
        clean = v.replace("[", "").replace("]", "").replace("hxxp", "http")
        if not _URL_RE.match(clean) or len(clean) < 12:
            return False
        # reject URLs that are just references to benign sites
        try:
            host = clean.split("/")[2].split(":")[0]
            if _is_benign_domain(host):
                return False
        except IndexError:
            return False
        return True
    if ioc_type == "email":
        return bool(_EMAIL_RE.match(v))
    return False


def _get_or_create_actor(db: Session, name: str) -> ThreatActor:
    name = name.strip()
    name_lower = name.lower()
    # Exact name match
    actor = db.query(ThreatActor).filter(ThreatActor.name == name).first()
    if actor:
        return actor
    # Case-insensitive name match or alias match
    for a in db.query(ThreatActor).all():
        if a.name.lower() == name_lower:
            return a
        if a.aliases and any(alias.lower() == name_lower for alias in a.aliases):
            return a
    actor = ThreatActor(name=name)
    db.add(actor)
    db.flush()
    return actor


async def enrich_one(db: Session, article: Article) -> bool:
    if not article.scraped_text:
        article.enrichment_status = "no_text"
        db.commit()
        return False

    try:
        result = await enrich_article(article.title, article.scraped_text)
    except Exception as e:
        logger.error("Enrichment failed for article %s: %s", article.id, e)
        article.enrichment_status = "error"
        db.commit()
        return False

    article.ai_summary = result.summary
    article.threat_category = result.threat_category
    article.ai_severity_score = result.severity_score
    article.sector_targets = result.sector_targets
    article.geo_origin = result.geo_origin
    article.geo_targets = result.geo_targets
    article.enrichment_status = "enriched"
    article.enriched_at = datetime.now(timezone.utc)

    db.query(IOC).filter(IOC.article_id == article.id).delete()
    for ioc in result.iocs:
        if ioc.ioc_confidence == "low":
            continue
        if ioc.value in _whitelist:
            logger.debug("Skipped whitelisted IOC [%s] %r", ioc.ioc_type, ioc.value[:60])
            continue
        if not _validate_ioc(ioc.ioc_type, ioc.value):
            logger.debug("Rejected IOC [%s] %r (confidence=%s)", ioc.ioc_type, ioc.value[:60], ioc.ioc_confidence)
            continue
        db.add(IOC(article_id=article.id, ioc_type=ioc.ioc_type, value=ioc.value))

    db.query(TTPTag).filter(TTPTag.article_id == article.id).delete()
    for ttp in result.ttps:
        db.add(TTPTag(
            article_id=article.id,
            technique_id=ttp.technique_id,
            technique_name=ttp.technique_name,
            tactic=ttp.tactic,
        ))

    db.query(ArticleActor).filter(ArticleActor.article_id == article.id).delete()
    for name in result.threat_actors:
        actor = _get_or_create_actor(db, name)
        db.add(ArticleActor(article_id=article.id, actor_id=actor.id))

    db.query(CVEMention).filter(CVEMention.article_id == article.id).delete()
    for cve_id in result.cves:
        db.add(CVEMention(article_id=article.id, cve_id=cve_id))

    db.commit()
    return True


async def run_enrich_batch(db: Session) -> dict:
    global _whitelist
    _whitelist = {row.value for row in db.query(IOCWhitelist).all()}

    pending = (
        db.query(Article)
        .filter(Article.enrichment_status == "pending")
        .all()
    )

    run = job_state.start_run("enrich", total=len(pending))
    # Clear control flags when a fresh run starts
    job_state.set_paused("enrich", False)
    job_state.set_stopped("enrich", False)

    for article in pending:
        if job_state.is_stopped("enrich"):
            logger.info("Enrichment stopped after %d/%d articles", run.processed, run.total)
            job_state.finish_run(run, status="stopped")
            return run.to_dict()

        # Check pause flag before each article
        if job_state.is_paused("enrich"):
            logger.info("Enrichment paused after %d/%d articles", run.processed, run.total)
            job_state.finish_run(run, status="paused")
            return run.to_dict()

        run.current_title = article.title[:80]

        try:
            ok = await enrich_one(db, article)
        except Exception as e:
            ok = False
            run.errors.append(job_state.ArticleError(
                article_id=article.id,
                title=article.title[:80],
                error=str(e),
            ))

        run.processed += 1
        if ok:
            run.succeeded += 1
        else:
            run.failed += 1
            if not run.errors or run.errors[-1].article_id != article.id:
                run.errors.append(job_state.ArticleError(
                    article_id=article.id,
                    title=article.title[:80],
                    error=article.enrichment_status,
                ))

        if settings.ENRICH_DELAY_SECONDS > 0:
            await asyncio.sleep(settings.ENRICH_DELAY_SECONDS)

    job_state.finish_run(run, status="completed")
    logger.info("Enrichment complete: %d succeeded, %d failed", run.succeeded, run.failed)
    return run.to_dict()
