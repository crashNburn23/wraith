import asyncio
import ipaddress
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import Article, IOC, TTPTag, ThreatActor, ArticleActor, CVEMention, IOCWhitelist
from app.services.enrichment_prompt import enrich_article
from app.services.benign_domains import is_benign_domain
from app.services.corrections import corrections_prompt_block
from app.services import job_state, embeddings
from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── IOC validation ───────────────────────────────────────────────────────────

_VALID_IOC_TYPES = {"ip", "domain", "hash", "url", "email"}

import re

_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9\[\]]([a-zA-Z0-9\-\[\]]{0,61}[a-zA-Z0-9\[\]])?(\.[a-zA-Z0-9\[\]\-]+)+$")
_MD5_RE   = re.compile(r"^[0-9a-fA-F]{32}$")
_SHA1_RE  = re.compile(r"^[0-9a-fA-F]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_URL_RE   = re.compile(r"^https?://", re.IGNORECASE)
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


def _is_valid_ip(value: str) -> bool:
    """Validates IPv4/IPv6 including defanged forms like 1.2.3[.]4."""
    clean = value.replace("[", "").replace("]", "")
    try:
        ipaddress.ip_address(clean)
        return True
    except ValueError:
        return False


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
        return _is_valid_ip(v)
    if ioc_type == "domain":
        if is_benign_domain(v):
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
            if is_benign_domain(host):
                return False
        except IndexError:
            return False
        return True
    if ioc_type == "email":
        return bool(_EMAIL_RE.match(v))
    return False


def _load_whitelist(db: Session) -> set[str]:
    return {row.value for row in db.query(IOCWhitelist).all()}


def _load_actor_cache(db: Session) -> dict[str, ThreatActor]:
    """name/alias (lowercase) → actor, built once per run to avoid per-name table scans."""
    cache: dict[str, ThreatActor] = {}
    for a in db.query(ThreatActor).all():
        cache[a.name.lower()] = a
        for alias in (a.aliases or []):
            cache.setdefault(alias.lower(), a)
    return cache


def _get_or_create_actor(db: Session, name: str, cache: dict[str, ThreatActor]) -> ThreatActor:
    name = name.strip()
    actor = cache.get(name.lower())
    if actor:
        return actor
    actor = ThreatActor(name=name)
    db.add(actor)
    db.flush()
    cache[name.lower()] = actor
    return actor


async def enrich_one(
    db: Session,
    article: Article,
    whitelist: set[str] | None = None,
    actor_cache: dict[str, ThreatActor] | None = None,
    corrections_block: str | None = None,
) -> bool:
    if not article.scraped_text:
        article.enrichment_status = "no_text"
        db.commit()
        return False

    # Single-article path: load context fresh so whitelist/corrections apply
    if whitelist is None:
        whitelist = _load_whitelist(db)
    if actor_cache is None:
        actor_cache = _load_actor_cache(db)
    if corrections_block is None:
        corrections_block = corrections_prompt_block(db)

    try:
        result = await enrich_article(article.title, article.scraped_text, corrections_block)
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

    # Semantic embedding (optional, graceful no-op when disabled)
    vec = await embeddings.embed_text(f"{article.title}\n{result.summary}")
    if vec:
        article.embedding = vec

    db.query(IOC).filter(IOC.article_id == article.id).delete()
    for ioc in result.iocs:
        if ioc.ioc_confidence == "low":
            continue
        if ioc.value in whitelist:
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
        actor = _get_or_create_actor(db, name, actor_cache)
        db.add(ArticleActor(article_id=article.id, actor_id=actor.id))

    db.query(CVEMention).filter(CVEMention.article_id == article.id).delete()
    for cve_id in result.cves:
        db.add(CVEMention(article_id=article.id, cve_id=cve_id))

    db.commit()
    return True


async def run_enrich_batch(db: Session) -> dict:
    # Per-run context, loaded once: whitelist, actor cache, correction memory.
    # Pause/stop flags are NOT cleared here — the run/resume endpoints own them,
    # so a scheduled run cannot silently override a user's manual pause.
    whitelist = _load_whitelist(db)
    actor_cache = _load_actor_cache(db)
    corrections_block = corrections_prompt_block(db)

    pending = (
        db.query(Article)
        .filter(Article.enrichment_status == "pending")
        .all()
    )

    run = job_state.start_run("enrich", total=len(pending))

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
            ok = await enrich_one(db, article, whitelist, actor_cache, corrections_block)
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

        job_state.save_run(run)

        if settings.ENRICH_DELAY_SECONDS > 0:
            await asyncio.sleep(settings.ENRICH_DELAY_SECONDS)

    job_state.finish_run(run, status="completed")
    logger.info("Enrichment complete: %d succeeded, %d failed", run.succeeded, run.failed)
    return run.to_dict()
