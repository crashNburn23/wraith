from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.ops import SavedSearch

router = APIRouter(prefix="/searches", tags=["searches"])


class SavedSearchCreate(BaseModel):
    name: str
    filters: dict = {}
    alert_enabled: bool = False
    alert_severity_min: float = 0.0


class SavedSearchUpdate(BaseModel):
    name: str | None = None
    filters: dict | None = None
    alert_enabled: bool | None = None
    alert_severity_min: float | None = None


def _serialize(s: SavedSearch) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "filters": s.filters,
        "alert_enabled": s.alert_enabled,
        "alert_severity_min": s.alert_severity_min,
        "last_alerted_at": s.last_alerted_at.isoformat() if s.last_alerted_at else None,
        "match_count": s.match_count,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.get("")
def list_searches(db: Session = Depends(get_db)):
    searches = db.query(SavedSearch).order_by(SavedSearch.created_at.desc()).all()
    return [_serialize(s) for s in searches]


@router.post("")
def create_search(body: SavedSearchCreate, db: Session = Depends(get_db)):
    s = SavedSearch(
        name=body.name,
        filters=body.filters,
        alert_enabled=body.alert_enabled,
        alert_severity_min=body.alert_severity_min,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _serialize(s)


@router.patch("/{search_id}")
def update_search(search_id: str, body: SavedSearchUpdate, db: Session = Depends(get_db)):
    s = db.query(SavedSearch).filter(SavedSearch.id == search_id).first()
    if not s:
        raise HTTPException(404, "Saved search not found")
    if body.name is not None:
        s.name = body.name
    if body.filters is not None:
        s.filters = body.filters
    if body.alert_enabled is not None:
        s.alert_enabled = body.alert_enabled
    if body.alert_severity_min is not None:
        s.alert_severity_min = body.alert_severity_min
    db.commit()
    db.refresh(s)
    return _serialize(s)


@router.delete("/{search_id}")
def delete_search(search_id: str, db: Session = Depends(get_db)):
    s = db.query(SavedSearch).filter(SavedSearch.id == search_id).first()
    if not s:
        raise HTTPException(404, "Saved search not found")
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.post("/{search_id}/run")
def run_search(search_id: str, db: Session = Depends(get_db)):
    """Execute a saved search and return current matches."""
    from app.models import Article, ThreatActor, ArticleActor, TTPTag, CVEMention
    from sqlalchemy import or_

    s = db.query(SavedSearch).filter(SavedSearch.id == search_id).first()
    if not s:
        raise HTTPException(404, "Saved search not found")

    f = s.filters or {}
    query = db.query(Article).filter(Article.enrichment_status == "enriched")

    q = f.get("q", "")
    if q:
        query = query.filter(or_(Article.title.ilike(f"%{q}%"), Article.ai_summary.ilike(f"%{q}%")))
    if f.get("category"):
        query = query.filter(Article.threat_category == f["category"])
    if f.get("severity_min") is not None:
        query = query.filter(Article.ai_severity_score >= f["severity_min"])
    if f.get("actor"):
        actor_obj = db.query(ThreatActor).filter(ThreatActor.name.ilike(f"%{f['actor']}%")).first()
        if actor_obj:
            ids = [aa.article_id for aa in db.query(ArticleActor).filter(ArticleActor.actor_id == actor_obj.id).all()]
            query = query.filter(Article.id.in_(ids))
        else:
            return {"total": 0, "items": []}
    if f.get("ttp"):
        ids = [t.article_id for t in db.query(TTPTag).filter(TTPTag.technique_id == f["ttp"]).all()]
        query = query.filter(Article.id.in_(ids))
    if f.get("cve"):
        ids = [m.article_id for m in db.query(CVEMention).filter(CVEMention.cve_id.ilike(f"%{f['cve']}%")).all()]
        query = query.filter(Article.id.in_(ids))

    total = query.count()
    items = query.order_by(Article.ai_severity_score.desc()).limit(50).all()
    return {
        "total": total,
        "items": [
            {
                "id": a.id,
                "title": a.title,
                "url": a.url,
                "threat_category": a.threat_category,
                "ai_severity_score": a.ai_severity_score,
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "ai_summary": a.ai_summary,
            }
            for a in items
        ],
    }
