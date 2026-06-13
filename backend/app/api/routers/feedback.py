import re
import json
import logging
from datetime import datetime, timezone, timedelta
from collections import Counter
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.api.deps import get_db
from app.models import Article, Feedback, ReadStatus, UserProfile
from app.db.base import new_uuid
from app.services.scoring import _get_config, _get_profile
from app.services.llm_client import get_llm_client, is_anthropic
from app.services.prompt_safety import UNTRUSTED_CONTENT_RULE, untrusted_block
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class FeedbackCreate(BaseModel):
    article_id: str
    rating: int  # -1, 0, 1


class ReasonsUpdate(BaseModel):
    reason_tags: list[str]


class ReadStatusUpdate(BaseModel):
    status: str  # unread / acknowledged / dismissed


class NoteApply(BaseModel):
    text: str


VALID_REASON_TAGS = {
    "wrong_category", "wrong_sector", "wrong_actor", "wrong_ttp",
    "too_vague", "not_actionable",
}


# ─── LLM helper ───────────────────────────────────────────────────────────────

async def _llm_complete(prompt: str, max_tokens: int = 600) -> str:
    client = get_llm_client()
    try:
        if is_anthropic():
            resp = await client.messages.create(
                model=settings.LLM_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text
        else:
            import httpx
            resp = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                max_tokens=max_tokens,
                stream=False,
                messages=[{"role": "user", "content": prompt}],
                timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0),
            )
            return resp.choices[0].message.content
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        raise HTTPException(503, f"LLM unavailable: {e}")


# ─── Ratings ──────────────────────────────────────────────────────────────────

@router.post("")
def rate_article(body: FeedbackCreate, db: Session = Depends(get_db)):
    if body.rating not in (-1, 0, 1):
        raise HTTPException(400, "Rating must be -1, 0, or 1")
    article = db.query(Article).filter(Article.id == body.article_id).first()
    if not article:
        raise HTTPException(404, "Article not found")

    feedback = db.query(Feedback).filter(Feedback.article_id == body.article_id).first()
    if feedback:
        feedback.rating = body.rating
    else:
        feedback = Feedback(id=new_uuid(), article_id=body.article_id, rating=body.rating)
        db.add(feedback)
    db.commit()
    return {"id": feedback.id, "rating": feedback.rating}


@router.patch("/{article_id}/reasons")
def update_reasons(article_id: str, body: ReasonsUpdate, db: Session = Depends(get_db)):
    invalid = set(body.reason_tags) - VALID_REASON_TAGS
    if invalid:
        raise HTTPException(400, f"Invalid reason tags: {sorted(invalid)}")
    fb = db.query(Feedback).filter(Feedback.article_id == article_id).first()
    if not fb:
        raise HTTPException(404, "No feedback found for this article — rate it first")
    fb.reason_tags = body.reason_tags or None
    db.commit()
    return {"article_id": article_id, "rating": fb.rating, "reason_tags": fb.reason_tags or []}


@router.get("/article/{article_id}")
def get_article_feedback(article_id: str, db: Session = Depends(get_db)):
    fb = db.query(Feedback).filter(Feedback.article_id == article_id).first()
    return {
        "article_id": article_id,
        "rating": fb.rating if fb else None,
    }


# ─── Read status ──────────────────────────────────────────────────────────────

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


# ─── LLM: preference summary ──────────────────────────────────────────────────

@router.post("/summarize")
async def summarize_feedback(db: Session = Depends(get_db)):
    """Generate a 2-3 sentence natural language summary of what the analyst likes and skips."""
    config = _get_config(db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.feedback_lookback_days)

    fb_rows = db.query(Feedback).filter(
        Feedback.rating != 0, Feedback.updated_at >= cutoff
    ).all()
    dismissed = db.query(ReadStatus).filter(
        ReadStatus.status == "dismissed", ReadStatus.updated_at >= cutoff
    ).all()
    explicit_ids = {f.article_id for f in fb_rows}
    dismissed = [d for d in dismissed if d.article_id not in explicit_ids]

    if not fb_rows and not dismissed:
        return {"summary": None, "has_data": False}

    all_ids = list({f.article_id for f in fb_rows} | {d.article_id for d in dismissed})
    articles_map = {
        a.id: a
        for a in db.query(Article).filter(Article.id.in_(all_ids)).all()
    }

    liked = [articles_map[f.article_id] for f in fb_rows if f.rating > 0 and f.article_id in articles_map]
    disliked_explicit = [articles_map[f.article_id] for f in fb_rows if f.rating < 0 and f.article_id in articles_map]
    dismissed_arts = [articles_map[d.article_id] for d in dismissed if d.article_id in articles_map]
    disliked_all = disliked_explicit + dismissed_arts

    def top(counter, n=3):
        return ", ".join(f"{k} ({v})" for k, v in counter.most_common(n)) or "none"

    liked_cats    = Counter(a.threat_category for a in liked if a.threat_category)
    liked_sectors = Counter(s for a in liked for s in (a.sector_targets or []))
    skip_cats     = Counter(a.threat_category for a in disliked_all if a.threat_category)
    skip_sectors  = Counter(s for a in disliked_all for s in (a.sector_targets or []))
    reason_counts = Counter(
        tag
        for f in fb_rows if f.rating < 0 and f.reason_tags
        for tag in f.reason_tags
    )

    prompt = f"""Summarize the following CTI analyst feedback data in 2-3 concise, specific sentences.
Address the analyst directly using "you". Focus on clear patterns — what they engage with and what they skip.
Mention specific threat categories and sectors where relevant. End with one actionable suggestion if appropriate.
Write only the sentences — no headers, no bullets, no markdown.

LIKED ({len(liked)} articles):
- Threat categories: {top(liked_cats)}
- Sectors: {top(liked_sectors)}

SKIPPED/NOT RELEVANT ({len(disliked_all)} total, {len(dismissed_arts)} dismissed):
- Threat categories: {top(skip_cats)}
- Sectors: {top(skip_sectors)}
- Stated reasons: {top(reason_counts)}"""

    summary = await _llm_complete(prompt, max_tokens=300)
    return {"summary": summary.strip(), "has_data": True}


# ─── LLM: natural language preference extraction ──────────────────────────────

@router.post("/notes/apply")
async def apply_note(body: NoteApply, db: Session = Depends(get_db)):
    """Parse natural language feedback into structured profile preferences and merge them in."""
    if not body.text.strip():
        raise HTTPException(400, "Text cannot be empty")

    prompt = f"""Extract topic preferences from this CTI analyst's feedback.
{UNTRUSTED_CONTENT_RULE}
Return ONLY a valid JSON object with exactly these four keys (values must be lists of lowercase strings):
- "sectors": industry sectors of interest (e.g. "healthcare", "financial services", "critical infrastructure")
- "categories": threat categories of interest (e.g. "ransomware", "phishing", "supply chain attack")
- "keywords": specific techniques or topics (e.g. "zero-day", "lateral movement", "living off the land")
- "threat_actors": threat actor or group names (e.g. "apt28", "lazarus group", "scattered spider")

Use lowercase. Return empty lists for keys with nothing applicable.
Return ONLY the JSON object — no explanation, no markdown, no code fences.

{untrusted_block("analyst_feedback", body.text.strip(), 4000)}
"""

    raw = await _llm_complete(prompt, max_tokens=400)

    # Strip markdown fences if the LLM wraps output
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not m:
        raise HTTPException(422, "LLM returned unexpected format — try rephrasing your input")
    try:
        extracted = json.loads(m.group())
    except json.JSONDecodeError:
        raise HTTPException(422, "LLM returned invalid JSON — try rephrasing your input")

    # Normalise: ensure all four keys exist as clean lowercase string lists
    parsed = {}
    for key in ("sectors", "categories", "keywords", "threat_actors"):
        vals = extracted.get(key, [])
        parsed[key] = [str(v).lower().strip() for v in vals if str(v).strip()]

    # Merge additively into UserProfile
    from sqlalchemy.orm.attributes import flag_modified
    profile = _get_profile(db)

    def _merge(existing: list | None, new_vals: list) -> tuple[list, list]:
        ex_lower = {v.lower() for v in (existing or [])}
        added = [v for v in new_vals if v.lower() not in ex_lower]
        return (existing or []) + added, added

    profile.sectors,       added_sectors  = _merge(profile.sectors,       parsed["sectors"])
    profile.categories,    added_cats     = _merge(profile.categories,    parsed["categories"])
    profile.keywords,      added_kw       = _merge(profile.keywords,      parsed["keywords"])
    profile.threat_actors, added_actors   = _merge(profile.threat_actors, parsed["threat_actors"])

    for field in ("sectors", "categories", "keywords", "threat_actors"):
        flag_modified(profile, field)
    db.commit()

    return {
        "extracted": parsed,
        "added": {
            "sectors":       added_sectors,
            "categories":    added_cats,
            "keywords":      added_kw,
            "threat_actors": added_actors,
        },
        "profile": {
            "sectors":       profile.sectors or [],
            "categories":    profile.categories or [],
            "keywords":      profile.keywords or [],
            "threat_actors": profile.threat_actors or [],
        },
    }
