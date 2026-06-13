import logging
import re

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Literal
from pydantic import BaseModel
from app.api.deps import get_db
from app.db.session import SessionLocal
from app.models import Article, IOC, TTPTag, ArticleActor, CVEMention, IOCWhitelist
from app.services import job_state
from app.services.corrections import record_correction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enrich", tags=["enrich"])


class EntityPatch(BaseModel):
    value: str | None = None
    user_note: str | None = None
    delete: bool = False


class WhitelistAdd(BaseModel):
    value: str
    ioc_type: str
    note: str | None = None


_TTP_ID_RE = re.compile(r"^T\d{4}(?:\.\d{3})?$", re.IGNORECASE)
_CVE_ID_RE = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)


@router.post("/run")
async def run_enrichment(background_tasks: BackgroundTasks):
    run = job_state.get_run("enrich")
    if run and run.status == "running":
        raise HTTPException(409, "Enrichment already running. Stop or wait for it to finish.")

    job_state.set_stopped("enrich", False)
    job_state.set_paused("enrich", False)

    from app.services.enrichment_runner import run_enrich_batch

    async def _run():
        # Own session: the request-scoped one is closed before background tasks run
        session = SessionLocal()
        try:
            await run_enrich_batch(session)
        except Exception:
            logger.exception("Enrichment batch failed")
        finally:
            session.close()

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
        "stopped": job_state.is_stopped("enrich"),
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


@router.post("/stop")
def stop_enrichment():
    run = job_state.get_run("enrich")
    if not run or run.status != "running":
        raise HTTPException(400, "No enrichment run is currently active.")
    job_state.set_stopped("enrich", True)
    return {"status": "stop_requested", "message": "Will stop after the current article finishes."}


@router.post("/resume")
async def resume_enrichment(background_tasks: BackgroundTasks):
    job_state.set_paused("enrich", False)
    run = job_state.get_run("enrich")
    if run and run.status == "running":
        return {"status": "already_running"}

    from app.services.enrichment_runner import run_enrich_batch

    async def _run():
        session = SessionLocal()
        try:
            await run_enrich_batch(session)
        except Exception:
            logger.exception("Enrichment batch failed")
        finally:
            session.close()

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


@router.post("/retry-errors")
def retry_errors(db: Session = Depends(get_db)):
    count = db.query(Article).filter(Article.enrichment_status == "error").update({"enrichment_status": "pending"})
    db.commit()
    return {"reset": count}


@router.post("/dismiss-errors")
def dismiss_errors(db: Session = Depends(get_db)):
    count = db.query(Article).filter(Article.enrichment_status == "error").update({"enrichment_status": "no_text"})
    db.commit()
    return {"dismissed": count}


@router.get("/whitelist")
def get_whitelist(db: Session = Depends(get_db)):
    items = db.query(IOCWhitelist).order_by(IOCWhitelist.created_at.desc()).all()
    return [
        {"id": i.id, "value": i.value, "ioc_type": i.ioc_type, "note": i.note,
         "created_at": i.created_at.isoformat()}
        for i in items
    ]


@router.post("/whitelist")
def add_to_whitelist(body: WhitelistAdd, db: Session = Depends(get_db)):
    existing = db.query(IOCWhitelist).filter(IOCWhitelist.value == body.value).first()
    if existing:
        return {"id": existing.id, "already_existed": True, "removed_iocs": 0}
    entry = IOCWhitelist(value=body.value, ioc_type=body.ioc_type, note=body.note)
    db.add(entry)
    # Retro-clean: whitelisting also removes existing IOC rows with this value
    removed = db.query(IOC).filter(IOC.value == body.value).delete(synchronize_session=False)
    record_correction(db, "ioc", "whitelisted", body.value)
    db.commit()
    db.refresh(entry)
    return {"id": entry.id, "already_existed": False, "removed_iocs": removed}


@router.delete("/whitelist/{item_id}")
def remove_from_whitelist(item_id: str, db: Session = Depends(get_db)):
    entry = db.query(IOCWhitelist).filter(IOCWhitelist.id == item_id).first()
    if not entry:
        raise HTTPException(404, "Whitelist entry not found")
    db.delete(entry)
    db.commit()
    return {"deleted": True}


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

    def _current_value() -> str:
        if entity_type == "ioc":
            return obj.value
        if entity_type == "ttp":
            return obj.technique_id
        if entity_type == "cve":
            return obj.cve_id
        return obj.actor.name if obj.actor else ""

    if body.delete:
        # Record the correction so future enrichment runs learn from it
        record_correction(db, entity_type, "deleted", _current_value())
        db.delete(obj)
        db.commit()
        return {"deleted": True}

    if body.user_note is not None:
        obj.user_note = body.user_note
    if body.value is not None:
        value = body.value.strip()
        if not value:
            raise HTTPException(400, "Entity value cannot be empty")
        if entity_type == "actor":
            raise HTTPException(400, "Actor renaming is not supported; edit the note or delete the article association")
        if entity_type == "ttp":
            if not _TTP_ID_RE.fullmatch(value):
                raise HTTPException(400, "TTP value must be a MITRE ATT&CK technique ID such as T1566 or T1059.003")
            value = value.upper()
        elif entity_type == "cve":
            if not _CVE_ID_RE.fullmatch(value):
                raise HTTPException(400, "CVE value must match CVE-YYYY-NNNN")
            value = value.upper()
        elif entity_type == "ioc":
            from app.services.enrichment_runner import _validate_ioc
            if not _validate_ioc(obj.ioc_type, value):
                raise HTTPException(400, f"Invalid {obj.ioc_type} IOC value")

        original = _current_value()
        if original and original != value:
            record_correction(db, entity_type, "edited", original, value)
        if entity_type == "ioc":
            obj.value = value
        elif entity_type == "ttp":
            obj.technique_id = value
        elif entity_type == "cve":
            obj.cve_id = value

    db.commit()
    return {"updated": True}
