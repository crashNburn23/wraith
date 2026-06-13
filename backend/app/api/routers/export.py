"""
Export endpoints — STIX 2.1, MISP, JSON, CSV.

All exports are streamed as file downloads.
"""
import csv
import io
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import Article, Bulletin
from app.models.investigation import Investigation
from app.services.stix_export import build_stix_bundle, build_misp_event

router = APIRouter(prefix="/export", tags=["export"])


def _articles_for_bulletin(db: Session, bulletin_date: str) -> list[Article]:
    bulletin = db.query(Bulletin).filter(Bulletin.bulletin_date == bulletin_date).first()
    if not bulletin:
        raise HTTPException(404, f"No bulletin for {bulletin_date}")
    articles = []
    for item in bulletin.items:
        a = db.query(Article).filter(Article.id == item.article_id).first()
        if a and a.enrichment_status == "enriched":
            articles.append(a)
    return articles


def _filter_articles(db: Session, q: str = "", category: str = "", severity_min: float = 0, limit: int = 100) -> list[Article]:
    from sqlalchemy import or_
    query = db.query(Article).filter(Article.enrichment_status == "enriched")
    if q:
        query = query.filter(or_(Article.title.ilike(f"%{q}%"), Article.ai_summary.ilike(f"%{q}%")))
    if category:
        query = query.filter(Article.threat_category == category)
    if severity_min:
        query = query.filter(Article.ai_severity_score >= severity_min)
    return query.order_by(Article.ai_severity_score.desc()).limit(limit).all()


# ─── STIX 2.1 ────────────────────────────────────────────────────────────────

@router.get("/stix/bulletin/{bulletin_date}")
def stix_bulletin(bulletin_date: str, db: Session = Depends(get_db)):
    articles = _articles_for_bulletin(db, bulletin_date)
    bundle = build_stix_bundle(articles)
    filename = f"wraith-stix-{bulletin_date}.json"
    return StreamingResponse(
        io.BytesIO(json.dumps(bundle, indent=2).encode()),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/stix/articles")
def stix_articles(
    db: Session = Depends(get_db),
    q: str = Query(""),
    category: str = Query(""),
    severity_min: float = Query(0),
    limit: int = Query(100, le=500),
):
    articles = _filter_articles(db, q, category, severity_min, limit)
    bundle = build_stix_bundle(articles)
    return StreamingResponse(
        io.BytesIO(json.dumps(bundle, indent=2).encode()),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="wraith-stix-articles.json"'},
    )


@router.get("/stix/investigation/{inv_id}")
def stix_investigation(inv_id: str, db: Session = Depends(get_db)):
    inv = db.query(Investigation).filter(Investigation.id == inv_id).first()
    if not inv:
        raise HTTPException(404, "Investigation not found")
    articles = [ia.article for ia in inv.articles if ia.article]
    bundle = build_stix_bundle(articles)
    safe_name = "".join(c if c.isalnum() else "-" for c in inv.name)[:40]
    filename = f"wraith-stix-inv-{safe_name}.json"
    return StreamingResponse(
        io.BytesIO(json.dumps(bundle, indent=2).encode()),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── MISP ────────────────────────────────────────────────────────────────────

@router.get("/misp/article/{article_id}")
def misp_article(article_id: str, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(404, "Article not found")
    event = build_misp_event(article)
    return StreamingResponse(
        io.BytesIO(json.dumps(event, indent=2).encode()),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="wraith-misp-{article_id[:8]}.json"'},
    )


@router.get("/misp/bulletin/{bulletin_date}")
def misp_bulletin(bulletin_date: str, db: Session = Depends(get_db)):
    articles = _articles_for_bulletin(db, bulletin_date)
    events = [build_misp_event(a) for a in articles]
    filename = f"wraith-misp-{bulletin_date}.json"
    return StreamingResponse(
        io.BytesIO(json.dumps({"response": events}, indent=2).encode()),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── JSON ─────────────────────────────────────────────────────────────────────

def _article_json(a: Article) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "url": a.url,
        "published_at": a.published_at.isoformat() if a.published_at else None,
        "threat_category": a.threat_category,
        "ai_severity_score": a.ai_severity_score,
        "ai_summary": a.ai_summary,
        "geo_origin": a.geo_origin,
        "geo_targets": a.geo_targets,
        "sector_targets": a.sector_targets,
        "iocs": [{"type": i.ioc_type, "value": i.value} for i in a.iocs],
        "cves": [m.cve_id for m in a.cve_mentions],
        "actors": [aa.actor.name for aa in a.article_actors if aa.actor],
        "ttps": [{"id": t.technique_id, "name": t.technique_name, "tactic": t.tactic} for t in a.ttp_tags],
    }


@router.get("/json/bulletin/{bulletin_date}")
def json_bulletin(bulletin_date: str, db: Session = Depends(get_db)):
    articles = _articles_for_bulletin(db, bulletin_date)
    payload = {"bulletin_date": bulletin_date, "articles": [_article_json(a) for a in articles]}
    filename = f"wraith-{bulletin_date}.json"
    return StreamingResponse(
        io.BytesIO(json.dumps(payload, indent=2).encode()),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/json/articles")
def json_articles(
    db: Session = Depends(get_db),
    q: str = Query(""),
    category: str = Query(""),
    severity_min: float = Query(0),
    limit: int = Query(100, le=1000),
):
    articles = _filter_articles(db, q, category, severity_min, limit)
    payload = {"articles": [_article_json(a) for a in articles]}
    return StreamingResponse(
        io.BytesIO(json.dumps(payload, indent=2).encode()),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="wraith-articles.json"'},
    )


# ─── CSV ──────────────────────────────────────────────────────────────────────

_CSV_FIELDS = ["title", "url", "published_at", "threat_category", "ai_severity_score",
               "geo_origin", "actors", "cves", "iocs", "sector_targets", "ai_summary"]


def _article_csv_row(a: Article) -> dict:
    return {
        "title": a.title,
        "url": a.url,
        "published_at": a.published_at.isoformat() if a.published_at else "",
        "threat_category": a.threat_category or "",
        "ai_severity_score": a.ai_severity_score or "",
        "geo_origin": a.geo_origin or "",
        "actors": "|".join(aa.actor.name for aa in a.article_actors if aa.actor),
        "cves": "|".join(m.cve_id for m in a.cve_mentions),
        "iocs": "|".join(f"{i.ioc_type}:{i.value}" for i in a.iocs),
        "sector_targets": "|".join(a.sector_targets or []),
        "ai_summary": (a.ai_summary or "").replace("\n", " "),
    }


@router.get("/csv/bulletin/{bulletin_date}")
def csv_bulletin(bulletin_date: str, db: Session = Depends(get_db)):
    articles = _articles_for_bulletin(db, bulletin_date)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS)
    writer.writeheader()
    for a in articles:
        writer.writerow(_article_csv_row(a))
    filename = f"wraith-{bulletin_date}.csv"
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/csv/articles")
def csv_articles(
    db: Session = Depends(get_db),
    q: str = Query(""),
    category: str = Query(""),
    severity_min: float = Query(0),
    limit: int = Query(500, le=5000),
):
    articles = _filter_articles(db, q, category, severity_min, limit)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS)
    writer.writeheader()
    for a in articles:
        writer.writerow(_article_csv_row(a))
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="wraith-articles.csv"'},
    )
