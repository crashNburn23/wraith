from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.investigation import Investigation, InvestigationArticle, InvestigationNote
from app.models import Article

router = APIRouter(prefix="/investigations", tags=["investigations"])


class InvestigationCreate(BaseModel):
    name: str
    description: str | None = None


class InvestigationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None  # open | closed


class AddArticle(BaseModel):
    article_id: str
    note: str | None = None


class AddNote(BaseModel):
    content: str


def _serialize_inv(inv: Investigation, article_count: int = 0) -> dict:
    return {
        "id": inv.id,
        "name": inv.name,
        "description": inv.description,
        "status": inv.status,
        "article_count": article_count,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "updated_at": inv.updated_at.isoformat() if inv.updated_at else None,
    }


def _serialize_article(ia: InvestigationArticle) -> dict:
    a = ia.article
    return {
        "id": ia.id,
        "article_id": ia.article_id,
        "note": ia.note,
        "added_at": ia.created_at.isoformat() if ia.created_at else None,
        "article": {
            "id": a.id,
            "title": a.title,
            "url": a.url,
            "threat_category": a.threat_category,
            "ai_severity_score": a.ai_severity_score,
            "published_at": a.published_at.isoformat() if a.published_at else None,
            "ai_summary": a.ai_summary,
        } if a else None,
    }


@router.get("")
def list_investigations(db: Session = Depends(get_db)):
    invs = db.query(Investigation).order_by(Investigation.created_at.desc()).all()
    counts = {
        row[0]: row[1]
        for row in db.query(InvestigationArticle.investigation_id, func.count(InvestigationArticle.id))
        .group_by(InvestigationArticle.investigation_id)
        .all()
    }
    return [_serialize_inv(inv, counts.get(inv.id, 0)) for inv in invs]


@router.post("")
def create_investigation(body: InvestigationCreate, db: Session = Depends(get_db)):
    inv = Investigation(name=body.name, description=body.description)
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return _serialize_inv(inv)


@router.get("/{inv_id}")
def get_investigation(inv_id: str, db: Session = Depends(get_db)):
    inv = db.query(Investigation).filter(Investigation.id == inv_id).first()
    if not inv:
        raise HTTPException(404, "Investigation not found")
    articles = [_serialize_article(ia) for ia in inv.articles]
    notes = [
        {"id": n.id, "content": n.content, "created_at": n.created_at.isoformat() if n.created_at else None}
        for n in inv.notes
    ]
    return {**_serialize_inv(inv, len(articles)), "articles": articles, "notes": notes}


@router.patch("/{inv_id}")
def update_investigation(inv_id: str, body: InvestigationUpdate, db: Session = Depends(get_db)):
    inv = db.query(Investigation).filter(Investigation.id == inv_id).first()
    if not inv:
        raise HTTPException(404, "Investigation not found")
    if body.name is not None:
        inv.name = body.name
    if body.description is not None:
        inv.description = body.description
    if body.status is not None:
        if body.status not in ("open", "closed"):
            raise HTTPException(400, "status must be 'open' or 'closed'")
        inv.status = body.status
    db.commit()
    db.refresh(inv)
    return _serialize_inv(inv)


@router.delete("/{inv_id}")
def delete_investigation(inv_id: str, db: Session = Depends(get_db)):
    inv = db.query(Investigation).filter(Investigation.id == inv_id).first()
    if not inv:
        raise HTTPException(404, "Investigation not found")
    db.delete(inv)
    db.commit()
    return {"ok": True}


@router.post("/{inv_id}/articles")
def add_article(inv_id: str, body: AddArticle, db: Session = Depends(get_db)):
    inv = db.query(Investigation).filter(Investigation.id == inv_id).first()
    if not inv:
        raise HTTPException(404, "Investigation not found")
    article = db.query(Article).filter(Article.id == body.article_id).first()
    if not article:
        raise HTTPException(404, "Article not found")
    existing = (
        db.query(InvestigationArticle)
        .filter(InvestigationArticle.investigation_id == inv_id, InvestigationArticle.article_id == body.article_id)
        .first()
    )
    if existing:
        return {"already_added": True, "id": existing.id}
    ia = InvestigationArticle(investigation_id=inv_id, article_id=body.article_id, note=body.note)
    db.add(ia)
    db.commit()
    db.refresh(ia)
    return _serialize_article(ia)


@router.patch("/{inv_id}/articles/{ia_id}")
def update_article_note(inv_id: str, ia_id: str, body: dict, db: Session = Depends(get_db)):
    ia = db.query(InvestigationArticle).filter(
        InvestigationArticle.id == ia_id, InvestigationArticle.investigation_id == inv_id
    ).first()
    if not ia:
        raise HTTPException(404, "Not found")
    ia.note = body.get("note")
    db.commit()
    return {"ok": True}


@router.delete("/{inv_id}/articles/{ia_id}")
def remove_article(inv_id: str, ia_id: str, db: Session = Depends(get_db)):
    ia = db.query(InvestigationArticle).filter(
        InvestigationArticle.id == ia_id, InvestigationArticle.investigation_id == inv_id
    ).first()
    if not ia:
        raise HTTPException(404, "Not found")
    db.delete(ia)
    db.commit()
    return {"ok": True}


@router.post("/{inv_id}/notes")
def add_note(inv_id: str, body: AddNote, db: Session = Depends(get_db)):
    inv = db.query(Investigation).filter(Investigation.id == inv_id).first()
    if not inv:
        raise HTTPException(404, "Investigation not found")
    note = InvestigationNote(investigation_id=inv_id, content=body.content)
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"id": note.id, "content": note.content, "created_at": note.created_at.isoformat() if note.created_at else None}


@router.delete("/{inv_id}/notes/{note_id}")
def delete_note(inv_id: str, note_id: str, db: Session = Depends(get_db)):
    note = db.query(InvestigationNote).filter(
        InvestigationNote.id == note_id, InvestigationNote.investigation_id == inv_id
    ).first()
    if not note:
        raise HTTPException(404, "Not found")
    db.delete(note)
    db.commit()
    return {"ok": True}


@router.get("/{inv_id}/export")
def export_investigation(inv_id: str, db: Session = Depends(get_db)):
    """Export investigation as a portable JSON report."""
    inv = db.query(Investigation).filter(Investigation.id == inv_id).first()
    if not inv:
        raise HTTPException(404, "Investigation not found")
    articles = []
    for ia in inv.articles:
        a = ia.article
        if not a:
            continue
        articles.append({
            "title": a.title,
            "url": a.url,
            "published_at": a.published_at.isoformat() if a.published_at else None,
            "threat_category": a.threat_category,
            "ai_severity_score": a.ai_severity_score,
            "ai_summary": a.ai_summary,
            "geo_origin": a.geo_origin,
            "geo_targets": a.geo_targets,
            "sector_targets": a.sector_targets,
            "analyst_note": ia.note,
            "iocs": [{"type": i.ioc_type, "value": i.value} for i in a.iocs],
            "cves": [m.cve_id for m in a.cve_mentions],
            "actors": [aa.actor.name for aa in a.article_actors if aa.actor],
            "ttps": [{"id": t.technique_id, "name": t.technique_name} for t in a.ttp_tags],
        })
    notes = [{"content": n.content, "created_at": n.created_at.isoformat() if n.created_at else None} for n in inv.notes]
    return {
        "name": inv.name,
        "description": inv.description,
        "status": inv.status,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "articles": articles,
        "notes": notes,
    }
