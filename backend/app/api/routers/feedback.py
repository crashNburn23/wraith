from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.api.deps import get_db
from app.models import Article, Feedback, ReadStatus
from app.db.base import new_uuid

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackCreate(BaseModel):
    article_id: str
    rating: int  # -1, 0, 1


class ReadStatusUpdate(BaseModel):
    status: str  # unread / acknowledged / dismissed


@router.post("")
def rate_article(body: FeedbackCreate, db: Session = Depends(get_db)):
    if body.rating not in (-1, 0, 1):
        raise HTTPException(400, "Rating must be -1, 0, or 1")
    article = db.query(Article).filter(Article.id == body.article_id).first()
    if not article:
        raise HTTPException(404, "Article not found")

    feedback = Feedback(id=new_uuid(), article_id=body.article_id, rating=body.rating)
    db.add(feedback)
    db.commit()
    return {"id": feedback.id, "rating": body.rating}


@router.get("/article/{article_id}")
def get_article_feedback(article_id: str, db: Session = Depends(get_db)):
    rows = db.query(Feedback).filter(Feedback.article_id == article_id).all()
    return {
        "article_id": article_id,
        "ratings": [{"id": f.id, "rating": f.rating, "created_at": f.created_at} for f in rows],
        "net": sum(f.rating for f in rows),
    }


@router.patch("/read-status/{article_id}")
def update_read_status(article_id: str, body: ReadStatusUpdate, db: Session = Depends(get_db)):
    if body.status not in ("unread", "acknowledged", "dismissed"):
        raise HTTPException(400, "Invalid status")
    rs = db.query(ReadStatus).filter(ReadStatus.article_id == article_id).first()
    if rs:
        rs.status = body.status
    else:
        rs = ReadStatus(id=new_uuid(), article_id=article_id, status=body.status)
        db.add(rs)
    db.commit()
    return {"article_id": article_id, "status": body.status}


@router.get("/read-status/{article_id}")
def get_read_status(article_id: str, db: Session = Depends(get_db)):
    rs = db.query(ReadStatus).filter(ReadStatus.article_id == article_id).first()
    return {"article_id": article_id, "status": rs.status if rs else "unread"}
