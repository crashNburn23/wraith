import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import Article, IOC, TTPTag, ThreatActor, ArticleActor, CVEMention
from app.services.enrichment_prompt import enrich_article
from app.services import job_state
from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_or_create_actor(db: Session, name: str) -> ThreatActor:
    actor = db.query(ThreatActor).filter(ThreatActor.name == name).first()
    if not actor:
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
    pending = (
        db.query(Article)
        .filter(Article.enrichment_status == "pending")
        .all()
    )

    run = job_state.start_run("enrich", total=len(pending))
    # Clear pause flag when a fresh run starts
    job_state.set_paused("enrich", False)

    for article in pending:
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
