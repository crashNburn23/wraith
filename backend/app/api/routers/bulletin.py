import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import date, timedelta
from pydantic import BaseModel
from app.api.deps import get_db
from app.db.session import SessionLocal
from app.models import Bulletin, BulletinItem, Article, Feedback, ReadStatus
from app.schemas.bulletin import BulletinOut, BulletinSummary, BulletinItemOut, ScoreBreakdown
from app.schemas.article import ArticleListItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bulletin", tags=["bulletin"])


class BuildRequest(BaseModel):
    include_all: bool = False


def _serialize_item(
    item: BulletinItem,
    user_rating: int | None = None,
    user_reason_tags: list | None = None,
    read_status: str = "unread",
) -> BulletinItemOut:
    return BulletinItemOut(
        id=item.id,
        rank=item.rank,
        article=ArticleListItem.model_validate(item.article),
        score=ScoreBreakdown(
            computed_score=item.computed_score,
            score_ai_severity=item.score_ai_severity,
            score_feedback_signal=item.score_feedback_signal,
            score_profile_match=item.score_profile_match,
            score_kev_bonus=item.score_kev_bonus,
            score_recency=item.score_recency,
            raw_ai_severity=item.raw_ai_severity,
            raw_feedback_signal=item.raw_feedback_signal,
            raw_profile_match=item.raw_profile_match,
            raw_kev_bonus=item.raw_kev_bonus,
            raw_recency_factor=item.raw_recency_factor,
            feedback_signal_articles=item.feedback_signal_articles,
        ),
        user_rating=user_rating,
        user_reason_tags=user_reason_tags or [],
        read_status=read_status,
        cluster_id=item.cluster_id,
        is_cluster_lead=item.is_cluster_lead,
        cluster_size=item.cluster_size,
    )


def _bulk_user_state(db: Session, article_ids: list[str]) -> tuple[dict, dict, dict]:
    """Return (rating_map, reason_map, read_map) keyed by article_id."""
    if not article_ids:
        return {}, {}, {}
    rating_map, reason_map = {}, {}
    for f in db.query(Feedback).filter(Feedback.article_id.in_(article_ids)).all():
        rating_map[f.article_id] = f.rating
        reason_map[f.article_id] = f.reason_tags or []
    read_map = {
        rs.article_id: rs.status
        for rs in db.query(ReadStatus).filter(ReadStatus.article_id.in_(article_ids)).all()
    }
    return rating_map, reason_map, read_map


def _fresh_brief_sources(db: Session, brief: str | None) -> list[dict]:
    """Parse the SOURCES suffix and resolve titles fresh from the DB, so
    re-enriched articles show their current titles."""
    if not brief or "\n\nSOURCES:" not in brief:
        return []
    raw = brief.rsplit("\n\nSOURCES:", 1)[1]
    pairs = []
    for chunk in raw.split("||"):
        if "::" in chunk:
            sid, title = chunk.split("::", 1)
            pairs.append((sid.strip(), title.strip()))
    if not pairs:
        return []
    ids = [sid for sid, _ in pairs]
    current = {a.id: a.title for a in db.query(Article).filter(Article.id.in_(ids)).all()}
    return [
        {"id": sid, "title": current.get(sid, stored_title)}
        for sid, stored_title in pairs
    ]


def _new_since_yesterday(db: Session, bulletin: Bulletin) -> int:
    yesterday = (date.fromisoformat(bulletin.bulletin_date) - timedelta(days=1)).isoformat()
    prev = db.query(Bulletin).filter(Bulletin.bulletin_date == yesterday).first()
    if not prev:
        return len(bulletin.items)
    prev_ids = {i.article_id for i in prev.items}
    return sum(1 for i in bulletin.items if i.article_id not in prev_ids)


@router.get("/today")
def today_bulletin(db: Session = Depends(get_db)):
    today = date.today().isoformat()
    bulletin = db.query(Bulletin).filter(Bulletin.bulletin_date == today).first()
    if not bulletin:
        return {"bulletin": None, "message": "No bulletin for today. Use /bulletin/build to generate one."}

    article_ids = [i.article_id for i in bulletin.items]
    rating_map, reason_map, read_map = _bulk_user_state(db, article_ids)

    return {
        "id": bulletin.id,
        "bulletin_date": bulletin.bulletin_date,
        "generated_at": bulletin.generated_at,
        "brief": bulletin.brief,
        "brief_generated_at": bulletin.brief_generated_at,
        "brief_sources": _fresh_brief_sources(db, bulletin.brief),
        "new_count": _new_since_yesterday(db, bulletin),
        "items": [
            _serialize_item(
                i,
                rating_map.get(i.article_id),
                reason_map.get(i.article_id),
                read_map.get(i.article_id, "unread"),
            )
            for i in bulletin.items
        ],
    }


@router.get("/history", response_model=list[dict])
def bulletin_history(db: Session = Depends(get_db)):
    bulletins = db.query(Bulletin).order_by(Bulletin.bulletin_date.desc()).limit(30).all()
    return [
        {
            "id": b.id,
            "bulletin_date": b.bulletin_date,
            "generated_at": b.generated_at,
            "item_count": len(b.items),
        }
        for b in bulletins
    ]


@router.get("/{bulletin_date}")
def get_bulletin(bulletin_date: str, db: Session = Depends(get_db)):
    bulletin = db.query(Bulletin).filter(Bulletin.bulletin_date == bulletin_date).first()
    if not bulletin:
        raise HTTPException(404, "Bulletin not found")
    article_ids = [i.article_id for i in bulletin.items]
    rating_map, reason_map, read_map = _bulk_user_state(db, article_ids)
    return {
        "id": bulletin.id,
        "bulletin_date": bulletin.bulletin_date,
        "generated_at": bulletin.generated_at,
        "items": [
            _serialize_item(
                i,
                rating_map.get(i.article_id),
                reason_map.get(i.article_id),
                read_map.get(i.article_id, "unread"),
            )
            for i in bulletin.items
        ],
    }


@router.post("/rebuild-scores")
async def rebuild_all_scores(scope: str = "today", db: Session = Depends(get_db)):
    """Recompute scores and re-rank. scope=today is synchronous (bounded by
    BULLETIN_MAX_ITEMS); scope=all recomputes every historical bulletin in the
    background."""
    from app.services.scoring import compute_score, _get_config, _get_profile, build_feedback_context

    def _rebuild_one(session: Session, bulletin: Bulletin, config, profile, ctx) -> int:
        for item in bulletin.items:
            breakdown = compute_score(session, item.article, config, profile, ctx)
            for k, v in breakdown.items():
                setattr(item, k, v)
        for rank, item in enumerate(
            sorted(bulletin.items, key=lambda i: i.computed_score, reverse=True), start=1
        ):
            item.rank = rank
        return len(bulletin.items)

    if scope == "all":
        def _run_all():
            session = SessionLocal()
            try:
                config = _get_config(session)
                profile = _get_profile(session)
                ctx = build_feedback_context(session, config)
                total = 0
                for b in session.query(Bulletin).all():
                    total += _rebuild_one(session, b, config, profile, ctx)
                session.commit()
                logger.info("Rebuilt scores for all bulletins (%d items)", total)
            finally:
                session.close()

        await asyncio.to_thread(_run_all)
        return {"status": "completed", "scope": "all"}

    today = date.today().isoformat()
    bulletin = db.query(Bulletin).filter(Bulletin.bulletin_date == today).first()
    if not bulletin:
        raise HTTPException(404, "No bulletin found for today")

    config = _get_config(db)
    profile = _get_profile(db)
    ctx = build_feedback_context(db, config)
    count = _rebuild_one(db, bulletin, config, profile, ctx)
    db.commit()
    return {"recomputed": count, "scope": "today"}


@router.post("/build")
async def build_bulletin(background_tasks: BackgroundTasks, body: BuildRequest | None = None):
    from app.services.bulletin import build_bulletin as _build
    from app.services.brief import generate_brief

    include_all = bool(body and body.include_all)

    async def _run():
        # Own session: the request-scoped one is closed before background tasks run
        session = SessionLocal()
        try:
            await asyncio.to_thread(_build, session, None, include_all)
            await generate_brief(session)
        except Exception:
            logger.exception("Bulletin build failed")
        finally:
            session.close()

    background_tasks.add_task(_run)
    return {"status": "started", "include_all": include_all}


@router.post("/brief/generate")
async def generate_brief(background_tasks: BackgroundTasks):
    from app.services.brief import generate_brief as _gen

    async def _run():
        session = SessionLocal()
        try:
            await _gen(session)
        except Exception:
            logger.exception("Brief generation failed")
        finally:
            session.close()

    background_tasks.add_task(_run)
    return {"status": "started"}


@router.post("/rebuild-item/{item_id}")
def rebuild_item_score(item_id: str, db: Session = Depends(get_db)):
    """Recompute the score for a single bulletin item (e.g. after a feedback change)."""
    item = db.query(BulletinItem).filter(BulletinItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "BulletinItem not found")
    from app.services.scoring import compute_score
    breakdown = compute_score(db, item.article)
    for k, v in breakdown.items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return _serialize_item(item)


@router.get("/items/{item_id}/score-breakdown")
def item_score_breakdown(item_id: str, db: Session = Depends(get_db)):
    """Full score transparency for a single bulletin item."""
    item = db.query(BulletinItem).filter(BulletinItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "BulletinItem not found")
    from app.services.scoring import _get_config
    config = _get_config(db)
    return {
        "item_id": item_id,
        "article_id": item.article_id,
        "article_title": item.article.title,
        "computed_score": item.computed_score,
        "weights": {
            "ai_severity":    config.weight_ai_severity,
            "feedback_signal": config.weight_feedback_signal,
            "profile_match":  config.weight_profile_match,
            "kev_bonus":      config.weight_kev_bonus,
            "recency":        config.weight_recency,
        },
        "components": {
            "ai_severity": {
                "raw": item.raw_ai_severity,
                "weighted": item.score_ai_severity,
                "label": "AI-assigned severity (0–100, normalised)",
                "axis": "threat",
            },
            "kev_bonus": {
                "raw": item.raw_kev_bonus,
                "weighted": item.score_kev_bonus,
                "label": "Contains a CISA KEV CVE",
                "axis": "threat",
            },
            "feedback_signal": {
                "raw": item.raw_feedback_signal,
                "weighted": item.score_feedback_signal,
                "label": "Overlap with your past rated articles",
                "axis": "relevance",
                "contributing_articles": item.feedback_signal_articles or [],
            },
            "profile_match": {
                "raw": item.raw_profile_match,
                "weighted": item.score_profile_match,
                "label": "Match against your interest profile + watchlist",
                "axis": "relevance",
            },
            "recency": {
                "raw": item.raw_recency_factor,
                "weighted": item.score_recency,
                "label": f"Recency (half-life {config.recency_half_life_days}d)",
                "axis": "relevance",
            },
        },
    }
