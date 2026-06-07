from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.api.deps import get_db
from app.models import Article
from app.schemas.article import ArticleListItem, ArticleDetail, IOCOut, TTPOut, CVEMentionOut

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("", response_model=dict)
def list_articles(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    category: str | None = None,
    severity_min: float | None = None,
    q: str | None = None,
):
    query = db.query(Article)
    if status:
        query = query.filter(Article.enrichment_status == status)
    if category:
        query = query.filter(Article.threat_category == category)
    if severity_min is not None:
        query = query.filter(Article.ai_severity_score >= severity_min)
    if q:
        query = query.filter(
            or_(Article.title.ilike(f"%{q}%"), Article.ai_summary.ilike(f"%{q}%"))
        )
    total = query.count()
    items = (
        query.order_by(Article.published_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [ArticleListItem.model_validate(a) for a in items],
    }


@router.get("/{article_id}", response_model=ArticleDetail)
def get_article(article_id: str, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(404, "Article not found")

    out = ArticleDetail.model_validate(article)
    out.iocs = [IOCOut.model_validate(i) for i in article.iocs]
    out.ttp_tags = [TTPOut.model_validate(t) for t in article.ttp_tags]
    out.cve_mentions = [CVEMentionOut.model_validate(c) for c in article.cve_mentions]

    # Populate actor names
    from app.schemas.article import ActorOut
    actors = []
    for aa in article.article_actors:
        actors.append(ActorOut(
            id=aa.id,
            actor_id=aa.actor_id,
            actor_name=aa.actor.name if aa.actor else "Unknown",
            user_note=aa.user_note,
        ))
    out.article_actors = actors  # type: ignore[attr-defined]
    return out
