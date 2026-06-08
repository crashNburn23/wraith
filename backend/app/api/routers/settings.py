from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models import ScoringConfig, Feedback, ReadStatus, Article, UserProfile
from app.schemas.scoring import ScoringConfigOut, ScoringConfigUpdate
from app.services.scoring import _get_config, _get_profile
from app.services.scheduler import get_scheduler
from app.core.config import settings as app_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/scoring", response_model=ScoringConfigOut)
def get_scoring_config(db: Session = Depends(get_db)):
    return _get_config(db)


@router.patch("/scoring", response_model=ScoringConfigOut)
def update_scoring_config(body: ScoringConfigUpdate, db: Session = Depends(get_db)):
    config = _get_config(db)

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields provided")

    # Validate weights sum if any are being changed
    new_weights = {
        "weight_ai_severity":    updates.get("weight_ai_severity",    config.weight_ai_severity),
        "weight_feedback_signal": updates.get("weight_feedback_signal", config.weight_feedback_signal),
        "weight_profile_match":  updates.get("weight_profile_match",  config.weight_profile_match),
        "weight_kev_bonus":      updates.get("weight_kev_bonus",      config.weight_kev_bonus),
        "weight_recency":        updates.get("weight_recency",        config.weight_recency),
    }
    total = sum(new_weights.values())
    if abs(total - 1.0) > 0.001:
        raise HTTPException(
            422,
            f"Weights must sum to 1.0. Current proposed total: {total:.4f}"
        )

    for field, val in updates.items():
        setattr(config, field, val)

    db.commit()
    db.refresh(config)
    return config


@router.get("/feedback-signal")
def feedback_signal_transparency(db: Session = Depends(get_db)):
    """Full transparency on the feedback signal: what data it uses, where it lives, and which articles are driving it."""
    config = _get_config(db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.feedback_lookback_days)

    # Explicit non-zero ratings — use updated_at so re-ratings count freshly
    fb_rows = (
        db.query(Feedback)
        .filter(Feedback.rating != 0, Feedback.updated_at >= cutoff)
        .order_by(Feedback.updated_at.desc())
        .all()
    )
    explicit_ids = {r.article_id for r in fb_rows}

    # Dismissed = implicit -1
    dismissed_rows = (
        db.query(ReadStatus)
        .filter(ReadStatus.status == "dismissed", ReadStatus.updated_at >= cutoff)
        .order_by(ReadStatus.updated_at.desc())
        .all()
    )
    dismissed_rows = [d for d in dismissed_rows if d.article_id not in explicit_ids]

    all_article_ids = list(explicit_ids | {d.article_id for d in dismissed_rows})
    articles_map = {
        a.id: a
        for a in db.query(Article).filter(Article.id.in_(all_article_ids)).all()
    } if all_article_ids else {}

    def _features(art):
        if not art:
            return {}
        return {
            "threat_category": art.threat_category,
            "ttps": [t.technique_id for t in art.ttp_tags],
            "actors": [aa.actor.name for aa in art.article_actors if aa.actor],
            "sectors": art.sector_targets or [],
        }

    rated = []
    for fb in fb_rows:
        art = articles_map.get(fb.article_id)
        rated.append({
            "article_id": fb.article_id,
            "title": art.title if art else "(article deleted)",
            "rating": fb.rating,
            "source": "explicit",
            "reason_tags": fb.reason_tags or [],
            "rated_at": fb.updated_at.isoformat() if fb.updated_at else None,
            "features": _features(art),
        })
    for d in dismissed_rows:
        art = articles_map.get(d.article_id)
        rated.append({
            "article_id": d.article_id,
            "title": art.title if art else "(article deleted)",
            "rating": -1,
            "source": "dismissed",
            "reason_tags": [],
            "rated_at": d.updated_at.isoformat() if d.updated_at else None,
            "features": _features(art),
        })

    total_signals = len(fb_rows) + len(dismissed_rows)
    active = total_signals >= config.min_feedback_articles

    return {
        "status": "active" if active else "inactive",
        "active_reason": (
            f"{total_signals} signal(s) in window ({len(fb_rows)} rated, {len(dismissed_rows)} dismissed)"
            if active
            else f"Need {config.min_feedback_articles} signals, have {total_signals} in the last {config.feedback_lookback_days} days"
        ),
        "config": {
            "lookback_days": config.feedback_lookback_days,
            "min_feedback_articles": config.min_feedback_articles,
            "weight_in_score": config.weight_feedback_signal,
            "decay_half_life_days": config.feedback_decay_half_life_days,
        },
        "formula": (
            "For each signal (explicit rating or dismissed article) within the lookback window:\n"
            "  overlap_score = shared_features / (target_ttp_count + 2)\n"
            "  decay = exp(-ln(2) × age_days / decay_half_life_days)\n"
            "  effective_weight = overlap_score × decay\n"
            "  where shared_features = matching category + TTPs + actors + sectors\n"
            "  dismissed articles count as rating = -1\n"
            "weighted_mean = Σ(effective_weight × rating) / Σ(effective_weight)\n"
            "signal = (weighted_mean + 1) / 2   ← normalised to [0, 1]\n"
            "Only signals with at least one overlapping feature contribute."
        ),
        "storage": {
            "ratings_table": "feedback",
            "ratings_columns": ["id", "article_id", "rating (-1/0/1)", "updated_at"],
            "dismissed_table": "read_status (status=dismissed)",
            "contributing_articles_field": "bulletin_items.feedback_signal_articles (JSON array per item)",
            "config_table": "scoring_config",
            "config_columns": ["feedback_lookback_days", "min_feedback_articles", "weight_feedback_signal", "feedback_decay_half_life_days"],
        },
        "rated_articles": rated,
        "rated_in_window": total_signals,
    }


@router.get("/scheduler")
def scheduler_status():
    """Current APScheduler job schedule and next run times."""
    scheduler = get_scheduler()

    JOB_LABELS = {
        "ingest":    {"name": "RSS Ingest",    "config_key": "INGEST_HOUR"},
        "enrich":    {"name": "Enrichment",    "config_key": "ENRICH_HOUR"},
        "cve_sync":  {"name": "CVE Sync",      "config_key": "CVE_SYNC_HOUR"},
        "bulletin":  {"name": "Build Bulletin", "config_key": "BULLETIN_HOUR"},
    }

    jobs = []
    for job_id, meta in JOB_LABELS.items():
        job = scheduler.get_job(job_id)
        hour_utc = getattr(app_settings, meta["config_key"], None)
        next_run = None
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

        jobs.append({
            "id": job_id,
            "name": meta["name"],
            "hour_utc": hour_utc,
            "schedule": f"{hour_utc:02d}:00 UTC" if hour_utc is not None else "—",
            "next_run": next_run,
            "active": job is not None,
        })

    return {
        "running": scheduler.running,
        "jobs": jobs,
        "note": "Schedule hours are set via environment variables (INGEST_HOUR, ENRICH_HOUR, CVE_SYNC_HOUR, BULLETIN_HOUR). Restart the API to apply changes.",
    }


class UserProfileUpdate(BaseModel):
    sectors: Optional[list[str]] = None
    threat_actors: Optional[list[str]] = None
    categories: Optional[list[str]] = None
    keywords: Optional[list[str]] = None


@router.get("/profile")
def get_profile(db: Session = Depends(get_db)):
    p = _get_profile(db)
    return {
        "sectors":       p.sectors or [],
        "threat_actors": p.threat_actors or [],
        "categories":    p.categories or [],
        "keywords":      p.keywords or [],
    }


@router.patch("/profile")
def update_profile(body: UserProfileUpdate, db: Session = Depends(get_db)):
    from sqlalchemy.orm.attributes import flag_modified
    p = _get_profile(db)
    if body.sectors is not None:
        p.sectors = body.sectors
        flag_modified(p, "sectors")
    if body.threat_actors is not None:
        p.threat_actors = body.threat_actors
        flag_modified(p, "threat_actors")
    if body.categories is not None:
        p.categories = body.categories
        flag_modified(p, "categories")
    if body.keywords is not None:
        p.keywords = body.keywords
        flag_modified(p, "keywords")
    db.commit()
    db.refresh(p)
    return {
        "sectors":       p.sectors or [],
        "threat_actors": p.threat_actors or [],
        "categories":    p.categories or [],
        "keywords":      p.keywords or [],
    }


@router.post("/prune")
def run_prune(db: Session = Depends(get_db)):
    from app.services.pruning import prune
    return prune(db)


@router.post("/scoring/reset", response_model=ScoringConfigOut)
def reset_scoring_config(db: Session = Depends(get_db)):
    config = _get_config(db)
    config.weight_ai_severity = 0.35
    config.weight_feedback_signal = 0.20
    config.weight_profile_match = 0.25
    config.weight_kev_bonus = 0.10
    config.weight_recency = 0.10
    config.feedback_lookback_days = 90
    config.recency_half_life_days = 3.0
    config.min_feedback_articles = 3
    config.feedback_decay_half_life_days = 30.0
    db.commit()
    db.refresh(config)
    return config
