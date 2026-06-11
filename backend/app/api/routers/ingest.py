import logging

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.db.session import SessionLocal
from app.models import Source, Article
from app.services import job_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/run")
async def trigger_ingest(background_tasks: BackgroundTasks):
    run = job_state.get_run("ingest")
    if run and run.status == "running":
        raise HTTPException(409, "Ingest already running.")

    from app.services.ingest_runner import run_ingest

    async def _run():
        # Own session: the request-scoped one is closed before background tasks run
        session = SessionLocal()
        try:
            await run_ingest(session)
        except Exception:
            logger.exception("Ingest run failed")
        finally:
            session.close()

    background_tasks.add_task(_run)
    return {"status": "started"}


@router.get("/status")
def ingest_status(db: Session = Depends(get_db)):
    total = db.query(Article).count()
    pending = db.query(Article).filter(Article.enrichment_status == "pending").count()
    enriched = db.query(Article).filter(Article.enrichment_status == "enriched").count()
    no_text = db.query(Article).filter(Article.enrichment_status == "no_text").count()
    error = db.query(Article).filter(Article.enrichment_status == "error").count()
    sources_active = db.query(Source).filter(Source.is_active == True).count()
    run = job_state.get_run("ingest")
    return {
        "current_run": run.to_dict() if run else None,
        "articles": {
            "total": total,
            "pending": pending,
            "enriched": enriched,
            "no_text": no_text,
            "error": error,
        },
        "sources_active": sources_active,
    }
