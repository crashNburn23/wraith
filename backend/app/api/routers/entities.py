from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models import Article, IOC, CVEMention, CVERecord, ArticleActor, ThreatActor, TTPTag

router = APIRouter(prefix="/entities", tags=["entities"])

MAX_TEXT = 12_000  # chars returned for scraped_text


def _article_ctx(article: Article) -> dict:
    return {
        "id": article.id,
        "title": article.title,
        "url": article.url,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "ai_summary": article.ai_summary,
        "enrichment_status": article.enrichment_status,
        "scraped_text": (article.scraped_text or "")[:MAX_TEXT] if article.scraped_text else None,
        "entities": {
            "iocs": [
                {"id": i.id, "ioc_type": i.ioc_type, "value": i.value}
                for i in article.iocs
            ],
            "cve_mentions": [
                {"id": c.id, "cve_id": c.cve_id}
                for c in article.cve_mentions
            ],
            "actors": [
                {"id": aa.id, "actor_id": aa.actor_id, "name": aa.actor.name if aa.actor else "Unknown"}
                for aa in article.article_actors
            ],
            "ttps": [
                {"id": t.id, "technique_id": t.technique_id, "technique_name": t.technique_name, "tactic": t.tactic}
                for t in article.ttp_tags
            ],
        },
    }


@router.get("/cve/{cve_id:path}")
def cve_context(cve_id: str, db: Session = Depends(get_db)):
    record = db.query(CVERecord).filter(CVERecord.cve_id == cve_id).first()
    mentions = db.query(CVEMention).filter(CVEMention.cve_id == cve_id).all()
    articles = [_article_ctx(m.article) for m in mentions if m.article]
    return {
        "cve_id": cve_id,
        "record": {
            "cvss_score": record.cvss_score,
            "epss_score": record.epss_score,
            "epss_percentile": record.epss_percentile,
            "in_kev": record.in_kev,
            "kev_due_date": record.kev_due_date,
            "nvd_description": record.nvd_description,
        } if record else None,
        "articles": articles,
    }


@router.get("/ioc/{ioc_id}")
def ioc_context(ioc_id: str, db: Session = Depends(get_db)):
    ioc = db.query(IOC).filter(IOC.id == ioc_id).first()
    if not ioc:
        raise HTTPException(404, "IOC not found")

    same_value = db.query(IOC).filter(IOC.value == ioc.value, IOC.id != ioc_id).limit(10).all()
    other_article_ids = list({i.article_id for i in same_value})
    other_articles = []
    if other_article_ids:
        other_articles = [
            _article_ctx(a)
            for a in db.query(Article).filter(Article.id.in_(other_article_ids)).all()
        ]

    return {
        "ioc": {
            "id": ioc.id,
            "ioc_type": ioc.ioc_type,
            "value": ioc.value,
            "user_note": ioc.user_note,
        },
        "article": _article_ctx(ioc.article) if ioc.article else None,
        "other_articles": other_articles,
    }


@router.get("/actor/{actor_id}")
def actor_context(actor_id: str, db: Session = Depends(get_db)):
    actor = db.query(ThreatActor).filter(ThreatActor.id == actor_id).first()
    if not actor:
        raise HTTPException(404, "Actor not found")

    articles = [
        _article_ctx(aa.article)
        for aa in actor.article_actors
        if aa.article
    ]
    return {
        "actor": {
            "id": actor.id,
            "name": actor.name,
            "aliases": actor.aliases or [],
        },
        "articles": articles,
    }
