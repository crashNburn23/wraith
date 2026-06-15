import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models import (
    ScoringConfig, Feedback, ReadStatus, Article, UserProfile,
    BulletinItem, WatchlistItem, JobRunRecord, Source,
)
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

    # Implicit signals: dismissed = -1, acknowledged (opened/read) = +0.4
    implicit_rows = (
        db.query(ReadStatus)
        .filter(ReadStatus.status.in_(["dismissed", "acknowledged"]), ReadStatus.updated_at >= cutoff)
        .order_by(ReadStatus.updated_at.desc())
        .all()
    )
    implicit_rows = [d for d in implicit_rows if d.article_id not in explicit_ids]
    dismissed_rows = [d for d in implicit_rows if d.status == "dismissed"]
    acked_rows = [d for d in implicit_rows if d.status == "acknowledged"]

    all_article_ids = list(explicit_ids | {d.article_id for d in implicit_rows})
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
    for d in acked_rows:
        art = articles_map.get(d.article_id)
        rated.append({
            "article_id": d.article_id,
            "title": art.title if art else "(article deleted)",
            "rating": 0.4,
            "source": "acknowledged",
            "reason_tags": [],
            "rated_at": d.updated_at.isoformat() if d.updated_at else None,
            "features": _features(art),
        })

    total_signals = len(fb_rows) + len(implicit_rows)
    active = total_signals >= config.min_feedback_articles

    return {
        "status": "active" if active else "inactive",
        "active_reason": (
            f"{total_signals} signal(s) in window ({len(fb_rows)} rated, {len(dismissed_rows)} dismissed, {len(acked_rows)} read)"
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
            "  dismissed articles count as rating = -1; opened/acknowledged = +0.4\n"
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


@router.get("/observability")
def pipeline_observability(db: Session = Depends(get_db)):
    """Recent pipeline health derived from persisted run snapshots."""
    rows = (
        db.query(JobRunRecord)
        .order_by(JobRunRecord.started_at.desc())
        .limit(50)
        .all()
    )

    runs = []
    dead_letter = []
    by_job = {}
    estimated_input_tokens = 0
    estimated_output_tokens = 0
    for row in rows:
        payload = row.payload or {}
        elapsed = payload.get("elapsed_seconds")
        if elapsed is None and row.finished_at:
            finished_at = row.finished_at
            started_at = row.started_at
            if finished_at.tzinfo is None:
                finished_at = finished_at.replace(tzinfo=timezone.utc)
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            elapsed = max(0, round((finished_at - started_at).total_seconds(), 1))
        processed = payload.get("processed", 0)
        failed = payload.get("failed", 0)
        errors = payload.get("errors", [])
        source_errors = [
            {
                "title": source.get("name", "Unknown source"),
                "error": source.get("error") or "Feed fetch failed",
            }
            for source in payload.get("source_results", [])
            if source.get("status") == "error"
        ]
        run_errors = errors or source_errors
        run = {
            "id": row.id,
            "job_type": row.job_type,
            "status": row.status,
            "started_at": row.started_at.isoformat(),
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "elapsed_seconds": elapsed,
            "processed": processed,
            "succeeded": payload.get("succeeded", 0),
            "failed": failed or len(run_errors),
            "total": payload.get("total", 0),
            "errors": run_errors[-5:],
        }
        runs.append(run)
        estimated_input_tokens += payload.get("estimated_input_tokens", 0)
        estimated_output_tokens += payload.get("estimated_output_tokens", 0)

        stats = by_job.setdefault(row.job_type, {
            "runs": 0, "completed": 0, "partial_runs": 0, "failed_runs": 0,
            "total_duration_seconds": 0.0, "duration_samples": 0,
            "processed": 0, "failed_items": 0,
        })
        stats["runs"] += 1
        stats["completed"] += int(row.status == "completed")
        stats["partial_runs"] += int(row.status == "partial")
        stats["failed_runs"] += int(row.status in {"partial", "error", "interrupted"})
        stats["processed"] += processed
        stats["failed_items"] += run["failed"]
        if elapsed is not None:
            stats["total_duration_seconds"] += elapsed
            stats["duration_samples"] += 1

        for error in run_errors[-5:]:
            dead_letter.append({
                "run_id": row.id,
                "job_type": row.job_type,
                "started_at": row.started_at.isoformat(),
                **error,
            })

    for stats in by_job.values():
        samples = stats.pop("duration_samples")
        total_duration = stats.pop("total_duration_seconds")
        stats["avg_duration_seconds"] = round(total_duration / samples, 1) if samples else None
        stats["success_rate"] = round(stats["completed"] / stats["runs"], 3) if stats["runs"] else None

    return {
        "queue": {
            "enrichment_pending": db.query(Article).filter(Article.enrichment_status == "pending").count(),
            "enrichment_errors": db.query(Article).filter(Article.enrichment_status == "error").count(),
            "sources_failing": db.query(Source).filter(Source.consecutive_failures > 0).count(),
        },
        "summary": by_job,
        "recent_runs": runs[:20],
        "dead_letter": dead_letter[:20],
        "model_usage": {
            "available": bool(estimated_input_tokens or estimated_output_tokens),
            "estimated_input_tokens": estimated_input_tokens,
            "estimated_output_tokens": estimated_output_tokens,
            "estimated_total_tokens": estimated_input_tokens + estimated_output_tokens,
            "estimated_cost_usd": None,
            "note": "Token counts are character-based estimates. Dollar cost is unavailable because provider pricing is not configured.",
        },
    }


class UserProfileUpdate(BaseModel):
    sectors: Optional[list[str]] = None
    threat_actors: Optional[list[str]] = None
    categories: Optional[list[str]] = None
    keywords: Optional[list[str]] = None
    geo_targets: Optional[list[str]] = None
    geo_origins: Optional[list[str]] = None


class ModelComparisonRequest(BaseModel):
    model_a: str
    model_b: str
    sample_size: int = 3


@router.post("/model-comparison")
async def model_comparison(body: ModelComparisonRequest, db: Session = Depends(get_db)):
    models = [body.model_a.strip(), body.model_b.strip()]
    if any(not model or len(model) > 200 for model in models):
        raise HTTPException(400, "Both model names are required and must be at most 200 characters")
    if models[0] == models[1]:
        raise HTTPException(400, "Choose two different models")
    if not 1 <= body.sample_size <= 5:
        raise HTTPException(400, "sample_size must be between 1 and 5")

    from app.services.model_comparison import article_case, compare_models, gold_case

    gold_path = Path(__file__).parents[3] / "data" / "gold_set.json"
    cases = []
    using_gold = False
    baseline = "Current stored enrichment, not a manually reviewed gold set"
    if gold_path.exists():
        try:
            gold = json.loads(gold_path.read_text())
            cases = [gold_case(case, i) for i, case in enumerate(gold[:body.sample_size])]
            if cases:
                using_gold = True
                baseline = f"Reviewed gold set ({gold_path.name})"
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(500, f"Could not load gold set: {exc}") from exc
    if not cases:
        articles = (
            db.query(Article)
            .filter(Article.enrichment_status == "enriched", Article.scraped_text.isnot(None))
            .order_by(Article.enriched_at.desc())
            .limit(body.sample_size)
            .all()
        )
        cases = [article_case(article) for article in articles]
    if not cases:
        raise HTTPException(400, "No gold-set cases or enriched articles with retained text are available")

    result = await compare_models(cases, models)
    return {
        **result,
        "sample_size": len(cases),
        "baseline": baseline,
        "gold_set": using_gold,
        "note": "Comparison is read-only and does not replace stored enrichment.",
    }


def _profile_to_dict(p) -> dict:
    return {
        "sectors":       p.sectors or [],
        "threat_actors": p.threat_actors or [],
        "categories":    p.categories or [],
        "keywords":      p.keywords or [],
        "geo_targets":   p.geo_targets or [],
        "geo_origins":   p.geo_origins or [],
    }


@router.get("/profile")
def get_profile(db: Session = Depends(get_db)):
    return _profile_to_dict(_get_profile(db))


@router.patch("/profile")
def update_profile(body: UserProfileUpdate, db: Session = Depends(get_db)):
    from sqlalchemy.orm.attributes import flag_modified
    p = _get_profile(db)
    for field in ("sectors", "threat_actors", "categories", "keywords", "geo_targets", "geo_origins"):
        val = getattr(body, field)
        if val is not None:
            setattr(p, field, val)
            flag_modified(p, field)
    db.commit()
    db.refresh(p)
    return _profile_to_dict(p)


@router.post("/prune")
def run_prune(db: Session = Depends(get_db)):
    from app.services.pruning import prune
    return prune(db)


@router.get("/scoring/suggest")
def suggest_weights(db: Session = Depends(get_db)):
    """
    Suggest scoring weights from your own feedback history.

    Joins bulletin items (which store raw component scores) with explicit
    ratings, then sets each weight proportional to how well that component
    separates liked from disliked articles (difference of means). Transparent,
    no black box — apply with PATCH /settings/scoring.
    """
    MIN_TOTAL, MIN_PER_CLASS = 10, 3

    rows = (
        db.query(BulletinItem, Feedback.rating)
        .join(Feedback, Feedback.article_id == BulletinItem.article_id)
        .filter(Feedback.rating != 0)
        .all()
    )
    liked    = [item for item, r in rows if r > 0]
    disliked = [item for item, r in rows if r < 0]

    if len(rows) < MIN_TOTAL or len(liked) < MIN_PER_CLASS or len(disliked) < MIN_PER_CLASS:
        return {
            "available": False,
            "reason": (
                f"Need at least {MIN_TOTAL} rated bulletin items with {MIN_PER_CLASS}+ "
                f"likes and {MIN_PER_CLASS}+ dislikes — have {len(liked)} liked / "
                f"{len(disliked)} disliked."
            ),
        }

    components = {
        "weight_ai_severity":     "raw_ai_severity",
        "weight_feedback_signal": "raw_feedback_signal",
        "weight_profile_match":   "raw_profile_match",
        "weight_kev_bonus":       "raw_kev_bonus",
        "weight_recency":         "raw_recency_factor",
    }

    def mean(items, attr):
        vals = [getattr(i, attr) or 0.0 for i in items]
        return sum(vals) / len(vals) if vals else 0.0

    separation = {
        wkey: abs(mean(liked, attr) - mean(disliked, attr))
        for wkey, attr in components.items()
    }
    total_sep = sum(separation.values())
    if total_sep == 0:
        return {"available": False, "reason": "No component separates your likes from dislikes yet."}

    suggested = {k: round(v / total_sep, 2) for k, v in separation.items()}
    # fix rounding drift so weights sum to exactly 1.0
    drift = round(1.0 - sum(suggested.values()), 2)
    largest = max(suggested, key=suggested.get)
    suggested[largest] = round(suggested[largest] + drift, 2)

    config = _get_config(db)
    return {
        "available": True,
        "suggested": suggested,
        "current": {k: getattr(config, k) for k in components},
        "sample": {"liked": len(liked), "disliked": len(disliked)},
        "method": "weight ∝ |mean(component | liked) − mean(component | disliked)| over your rated bulletin items",
    }


class WatchlistAdd(BaseModel):
    item_type: str  # actor | cve | keyword
    value: str


@router.get("/watchlist")
def get_watchlist(db: Session = Depends(get_db)):
    items = db.query(WatchlistItem).order_by(WatchlistItem.created_at.desc()).all()
    return [
        {"id": i.id, "item_type": i.item_type, "value": i.value, "created_at": i.created_at.isoformat()}
        for i in items
    ]


@router.post("/watchlist")
def add_watchlist(body: WatchlistAdd, db: Session = Depends(get_db)):
    if body.item_type not in ("actor", "cve", "keyword"):
        raise HTTPException(400, "item_type must be actor, cve, or keyword")
    value = body.value.strip()
    if not value:
        raise HTTPException(400, "value cannot be empty")
    existing = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.item_type == body.item_type, WatchlistItem.value.ilike(value))
        .first()
    )
    if existing:
        return {"id": existing.id, "already_existed": True}
    item = WatchlistItem(item_type=body.item_type, value=value)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "already_existed": False}


@router.delete("/watchlist/{item_id}")
def remove_watchlist(item_id: str, db: Session = Depends(get_db)):
    item = db.query(WatchlistItem).filter(WatchlistItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Watchlist item not found")
    db.delete(item)
    db.commit()
    return {"deleted": True}


@router.post("/benign-domains/refresh")
async def refresh_benign_domains():
    """Download the Tranco top-sites list to expand the IOC false-positive filter."""
    from app.services.benign_domains import refresh_from_tranco
    try:
        count = await refresh_from_tranco()
    except Exception as e:
        raise HTTPException(502, f"Download failed: {e}")
    return {"domains": count}


@router.get("/models")
async def list_local_models():
    """Return locally installed model names from the configured LLM provider."""
    from app.services.llm_client import is_anthropic
    if is_anthropic():
        return {"models": [], "provider": "anthropic"}
    import httpx
    base = app_settings.LLM_BASE_URL.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base}/models")
            resp.raise_for_status()
            data = resp.json()
        names = sorted(m["id"] for m in data.get("data", []))
        return {"models": names, "provider": "ollama"}
    except Exception:
        return {"models": [], "provider": "ollama"}


class SetModelRequest(BaseModel):
    model: str


@router.post("/model")
async def set_active_model(body: SetModelRequest):
    """Update the active LLM model in memory and persist it to .env."""
    model = body.model.strip()
    if not model or len(model) > 200:
        raise HTTPException(400, "Invalid model name")

    # Update in memory
    app_settings.LLM_MODEL = model

    # Clear the cached client so the next call picks up the new model
    from app.services.llm_client import get_llm_client
    get_llm_client.cache_clear()

    # Persist to .env — search cwd then parent for the file
    from pathlib import Path
    for candidate in [Path.cwd() / ".env", Path.cwd().parent / ".env"]:
        if candidate.exists():
            text = candidate.read_text()
            import re as _re
            if _re.search(r"^LLM_MODEL\s*=", text, _re.MULTILINE):
                text = _re.sub(r"^(LLM_MODEL\s*=).*", rf"\g<1>{model}", text, flags=_re.MULTILINE)
            else:
                text = text.rstrip("\n") + f"\nLLM_MODEL={model}\n"
            candidate.write_text(text)
            break

    return {"model": model}


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
