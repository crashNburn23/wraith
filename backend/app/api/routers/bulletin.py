import json
import re

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import date
from app.api.deps import get_db
from app.models import Bulletin, BulletinItem, Article, Feedback, ReadStatus
from app.schemas.bulletin import BulletinOut, BulletinSummary, BulletinItemOut, ScoreBreakdown
from app.schemas.article import ArticleListItem

router = APIRouter(prefix="/bulletin", tags=["bulletin"])


def _serialize_item(item: BulletinItem) -> BulletinItemOut:
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
    )


@router.get("/today")
def today_bulletin(db: Session = Depends(get_db)):
    today = date.today().isoformat()
    bulletin = db.query(Bulletin).filter(Bulletin.bulletin_date == today).first()
    if not bulletin:
        return {"bulletin": None, "message": "No bulletin for today. Use /bulletin/build to generate one."}

    return {
        "id": bulletin.id,
        "bulletin_date": bulletin.bulletin_date,
        "generated_at": bulletin.generated_at,
        "items": [_serialize_item(i) for i in bulletin.items],
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
    return {
        "id": bulletin.id,
        "bulletin_date": bulletin.bulletin_date,
        "generated_at": bulletin.generated_at,
        "items": [_serialize_item(i) for i in bulletin.items],
    }


class RerankRequest(BaseModel):
    bulletin_date: str
    prompt: str


@router.post("/rerank")
async def rerank_bulletin(body: RerankRequest, db: Session = Depends(get_db)):
    import httpx
    from app.services.llm_client import get_llm_client
    from app.core.config import settings

    bulletin = db.query(Bulletin).filter(Bulletin.bulletin_date == body.bulletin_date).first()
    if not bulletin:
        raise HTTPException(404, "Bulletin not found")
    if not bulletin.items:
        raise HTTPException(400, "Bulletin has no items")

    items = sorted(bulletin.items, key=lambda i: i.rank)
    lines = []
    for item in items:
        art = item.article
        summary = (art.ai_summary or "")[:180]
        cat = art.threat_category or ""
        lines.append(f'ID:{item.id} | {art.title} | {cat} | {summary}')

    llm_prompt = (
        f'You are a CTI analyst assistant. Re-prioritize this threat intelligence bulletin based on the analyst\'s focus:\n\n'
        f'FOCUS: "{body.prompt}"\n\n'
        f'Items (current rank order):\n' + "\n".join(f"{i+1}. {l}" for i, l in enumerate(lines)) +
        f'\n\nReturn ONLY a JSON array of the item IDs in your new priority order, most relevant first. '
        f'Include every ID exactly once. Example: ["id-a", "id-b", "id-c"]'
    )

    client = get_llm_client()
    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": llm_prompt}],
            timeout=httpx.Timeout(connect=10.0, read=90.0, write=10.0, pool=10.0),
        )
        raw = response.choices[0].message.content.strip()
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON array in LLM response: {raw[:200]}")
        ordered_ids = json.loads(match.group())
    except Exception as e:
        raise HTTPException(500, f"Rerank failed: {e}")

    item_map = {item.id: _serialize_item(item) for item in items}
    seen: set[str] = set()
    reranked = []
    for item_id in ordered_ids:
        if item_id in item_map and item_id not in seen:
            reranked.append(item_map[item_id])
            seen.add(item_id)
    for item in items:
        if item.id not in seen:
            reranked.append(item_map[item.id])

    return {"items": reranked, "prompt": body.prompt}


@router.post("/build")
def build_bulletin(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from app.services.bulletin import build_bulletin as _build

    def _run():
        _build(db)

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
                "label": "Match against your interest profile",
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
