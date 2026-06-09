from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.api.deps import get_db
from app.models import Article, IOC, ThreatActor, ArticleActor, TTPTag
from sqlalchemy import func

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def search(
    db: Session = Depends(get_db),
    q: str = Query(""),
    category: str | None = None,
    severity_min: float | None = None,
    actor: str | None = None,
    ttp: str | None = None,
    cve: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = db.query(Article).filter(Article.enrichment_status == "enriched")
    if q:
        query = query.filter(
            or_(Article.title.ilike(f"%{q}%"), Article.ai_summary.ilike(f"%{q}%"))
        )
    if category:
        query = query.filter(Article.threat_category == category)
    if severity_min is not None:
        query = query.filter(Article.ai_severity_score >= severity_min)
    if ttp:
        ttp_article_ids = [t.article_id for t in db.query(TTPTag).filter(TTPTag.technique_id == ttp).all()]
        query = query.filter(Article.id.in_(ttp_article_ids))
    if actor:
        actor_obj = db.query(ThreatActor).filter(ThreatActor.name.ilike(f"%{actor}%")).first()
        if actor_obj:
            actor_article_ids = [aa.article_id for aa in db.query(ArticleActor).filter(ArticleActor.actor_id == actor_obj.id).all()]
            query = query.filter(Article.id.in_(actor_article_ids))
        else:
            return {"total": 0, "items": []}
    if cve:
        from app.models import CVEMention
        cve_article_ids = [m.article_id for m in db.query(CVEMention).filter(CVEMention.cve_id.ilike(f"%{cve}%")).all()]
        query = query.filter(Article.id.in_(cve_article_ids))

    total = query.count()
    items = query.order_by(Article.ai_severity_score.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "items": [
            {
                "id": a.id,
                "title": a.title,
                "url": a.url,
                "threat_category": a.threat_category,
                "ai_severity_score": a.ai_severity_score,
                "published_at": a.published_at,
                "ai_summary": a.ai_summary,
            }
            for a in items
        ],
    }


@router.get("/ioc")
def search_ioc(db: Session = Depends(get_db), q: str = Query(default=""), ioc_type: str = Query(default="")):
    query = db.query(IOC)
    if q:
        query = query.filter(IOC.value.ilike(f"%{q}%"))
    if ioc_type:
        query = query.filter(IOC.ioc_type == ioc_type)
    iocs = query.order_by(IOC.created_at.desc()).limit(200).all()
    return [
        {
            "id": i.id,
            "ioc_type": i.ioc_type,
            "value": i.value,
            "article_id": i.article_id,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in iocs
    ]


@router.get("/actors")
def search_actors(db: Session = Depends(get_db), q: str = Query("")):
    query = db.query(ThreatActor)
    if q:
        query = query.filter(ThreatActor.name.ilike(f"%{q}%"))
    actors = query.order_by(ThreatActor.name).limit(50).all()
    if not actors:
        return []

    actor_ids = [a.id for a in actors]
    stats_rows = (
        db.query(
            ArticleActor.actor_id,
            func.count(ArticleActor.id).label("cnt"),
            func.max(Article.published_at).label("last_seen"),
        )
        .join(Article, Article.id == ArticleActor.article_id)
        .filter(ArticleActor.actor_id.in_(actor_ids))
        .group_by(ArticleActor.actor_id)
        .all()
    )
    stats = {row.actor_id: (row.cnt, row.last_seen) for row in stats_rows}

    return [
        {
            "id": a.id,
            "name": a.name,
            "aliases": a.aliases,
            "article_count": stats.get(a.id, (0, None))[0],
            "last_seen": stats.get(a.id, (0, None))[1].isoformat() if stats.get(a.id, (0, None))[1] else None,
        }
        for a in actors
    ]


@router.get("/actors/{actor_id}")
def get_actor(actor_id: str, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    actor = db.query(ThreatActor).filter(ThreatActor.id == actor_id).first()
    if not actor:
        raise HTTPException(404, "Actor not found")
    article_ids = [aa.article_id for aa in db.query(ArticleActor).filter(ArticleActor.actor_id == actor_id).all()]
    return {
        "id": actor.id,
        "name": actor.name,
        "aliases": actor.aliases,
        "article_count": len(article_ids),
        "article_ids": article_ids,
    }


@router.post("/actors/cleanup")
def cleanup_actors(db: Session = Depends(get_db)):
    actors = db.query(ThreatActor).all()
    orphaned = [a for a in actors if db.query(ArticleActor).filter(ArticleActor.actor_id == a.id).count() == 0]
    for actor in orphaned:
        db.delete(actor)
    db.commit()
    return {"removed": len(orphaned)}


@router.get("/tags")
def list_tags(db: Session = Depends(get_db)):
    tags = db.query(TTPTag.technique_id, TTPTag.technique_name).distinct().all()
    return [{"technique_id": t[0], "technique_name": t[1]} for t in tags]
