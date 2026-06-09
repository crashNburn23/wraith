import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.config import settings
from app.services import job_state

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def start_scheduler(app) -> None:
    from app.db.session import SessionLocal
    from app.services.ingest_runner import run_ingest
    from app.services.enrichment_runner import run_enrich_batch
    from app.services.cve_enrichment import sync_cves_for_articles
    from app.services.bulletin import build_bulletin
    from app.services.pruning import prune

    scheduler = get_scheduler()

    async def _ingest():
        run = job_state.get_run("ingest")
        if run and run.status == "running":
            logger.info("Skipping scheduled ingest — already running")
            return
        db = SessionLocal()
        try:
            await run_ingest(db)
        finally:
            db.close()

    async def _enrich():
        run = job_state.get_run("enrich")
        if run and run.status == "running":
            logger.info("Skipping scheduled enrichment — already running")
            return
        db = SessionLocal()
        try:
            await run_enrich_batch(db)
        finally:
            db.close()

    async def _cve_sync():
        db = SessionLocal()
        try:
            await sync_cves_for_articles(db)
        finally:
            db.close()

    def _bulletin():
        db = SessionLocal()
        try:
            build_bulletin(db)
        finally:
            db.close()

    def _prune():
        db = SessionLocal()
        try:
            prune(db)
        finally:
            db.close()

    scheduler.add_job(_ingest,   "cron", hour=settings.INGEST_HOUR,   minute=0, id="ingest")
    scheduler.add_job(_enrich,   "cron", hour=settings.ENRICH_HOUR,   minute=0, id="enrich")
    scheduler.add_job(_cve_sync, "cron", hour=settings.CVE_SYNC_HOUR, minute=0, id="cve_sync")
    scheduler.add_job(_bulletin, "cron", hour=settings.BULLETIN_HOUR, minute=0, id="bulletin")
    scheduler.add_job(_prune,    "cron", day_of_week="sun", hour=3,   minute=0, id="prune")

    scheduler.start()
    logger.info(
        "Scheduler started — ingest:%02d:00 enrich:%02d:00 cve:%02d:00 bulletin:%02d:00 UTC",
        settings.INGEST_HOUR, settings.ENRICH_HOUR, settings.CVE_SYNC_HOUR, settings.BULLETIN_HOUR,
    )


def stop_scheduler() -> None:
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
