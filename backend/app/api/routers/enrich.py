from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Literal
from pydantic import BaseModel
from app.api.deps import get_db
from app.models import Article, IOC, TTPTag, ArticleActor, CVEMention
from app.services import job_state

router = APIRouter(prefix="/enrich", tags=["enrich"])


class EntityPatch(BaseModel):
    value: str | None = None
    user_note: str | None = None
    delete: bool = False


@router.post("/run")
async def run_enrichment(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    run = job_state.get_run("enrich")
    if run and run.status == "running":
        raise HTTPException(409, "Enrichment already running. Pause or wait for it to finish.")

    from app.services.enrichment_runner import run_enrich_batch

    async def _run():
        await run_enrich_batch(db)

    background_tasks.add_task(_run)
    return {"status": "started"}


@router.get("/status")
def enrich_status(db: Session = Depends(get_db)):
    run = job_state.get_run("enrich")
    pending_count = db.query(Article).filter(Article.enrichment_status == "pending").count()
    enriched_count = db.query(Article).filter(Article.enrichment_status == "enriched").count()
    error_count = db.query(Article).filter(Article.enrichment_status == "error").count()
    return {
        "paused": job_state.is_paused("enrich"),
        "pending_articles": pending_count,
        "enriched_articles": enriched_count,
        "error_articles": error_count,
        "current_run": run.to_dict() if run else None,
    }


@router.post("/pause")
def pause_enrichment():
    run = job_state.get_run("enrich")
    if not run or run.status != "running":
        raise HTTPException(400, "No enrichment run is currently active.")
    job_state.set_paused("enrich", True)
    return {"status": "pause_requested", "message": "Will pause after the current article finishes."}


@router.post("/resume")
async def resume_enrichment(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    job_state.set_paused("enrich", False)
    run = job_state.get_run("enrich")
    if run and run.status == "running":
        return {"status": "already_running"}

    from app.services.enrichment_runner import run_enrich_batch

    async def _run():
        await run_enrich_batch(db)

    background_tasks.add_task(_run)
    return {"status": "resumed"}


@router.get("/prompt")
def get_enrichment_prompt():
    from app.services.enrichment_prompt import SYSTEM_PROMPT
    return {"prompt": SYSTEM_PROMPT}


@router.post("/articles/{article_id}")
async def enrich_single(article_id: str, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(404, "Article not found")
    from app.services.enrichment_runner import enrich_one
    ok = await enrich_one(db, article)
    return {"enriched": ok}


@router.patch("/entities/{entity_type}/{entity_id}")
def patch_entity(
    entity_type: Literal["ioc", "ttp", "actor", "cve"],
    entity_id: str,
    body: EntityPatch,
    db: Session = Depends(get_db),
):
    model_map = {"ioc": IOC, "ttp": TTPTag, "actor": ArticleActor, "cve": CVEMention}
    Model = model_map[entity_type]
    obj = db.query(Model).filter(Model.id == entity_id).first()
    if not obj:
        raise HTTPException(404, f"{entity_type} not found")

    if body.delete:
        db.delete(obj)
        db.commit()
        return {"deleted": True}

    if body.user_note is not None:
        obj.user_note = body.user_note
    if body.value is not None:
        if entity_type == "ioc":
            obj.value = body.value
        elif entity_type == "ttp":
            obj.technique_id = body.value
        elif entity_type == "cve":
            obj.cve_id = body.value

    db.commit()
    return {"updated": True}
