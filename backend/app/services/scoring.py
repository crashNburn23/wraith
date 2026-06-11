"""
Recommended score for bulletin items — two-axis model.

  Threat axis:    w_sev  × ai_severity/100  +  w_kev × kev_bonus
  Relevance axis: w_fb   × feedback_signal  +  w_profile × profile_match  +  w_rec × recency

All weights read from scoring_config; must sum to 1.0.

Feedback signal sources (strongest to weakest):
  explicit 👍/👎 rating  → ±1.0
  dismissed article      → −1.0 (implicit)
  acknowledged/opened    → +0.4 (implicit)

The expensive feedback/KEV/watchlist lookups are hoisted into a
FeedbackContext built once per bulletin build (previously these queries ran
per scored article — O(articles × feedback)).
"""
import math
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.models import (
    Article, Feedback, ReadStatus, CVERecord, ScoringConfig, UserProfile, WatchlistItem,
)
from app.services.embeddings import cosine

logger = logging.getLogger(__name__)

ACKNOWLEDGED_SIGNAL = 0.4   # implicit positive weight for opened/acknowledged articles
SEMANTIC_SIM_THRESHOLD = 0.55


def _get_config(db: Session) -> ScoringConfig:
    cfg = db.query(ScoringConfig).first()
    if not cfg:
        cfg = ScoringConfig()
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def _get_profile(db: Session) -> UserProfile:
    p = db.query(UserProfile).filter(UserProfile.id == 1).first()
    if not p:
        p = UserProfile(id=1, sectors=[], threat_actors=[], categories=[], keywords=[])
        db.add(p)
        db.commit()
        db.refresh(p)
    return p


@dataclass
class FeedbackContext:
    """Everything _feedback_signal/_kev_bonus/_profile_match need, fetched once."""
    signal_rows: dict = field(default_factory=dict)   # article_id → (rating: float, ts, reason_tags)
    past_articles: list = field(default_factory=list)
    kev_cves: set = field(default_factory=set)
    watch_actors: set = field(default_factory=set)    # lowercase actor names/values
    watch_cves: set = field(default_factory=set)
    watch_keywords: set = field(default_factory=set)


def build_feedback_context(db: Session, config: ScoringConfig) -> FeedbackContext:
    ctx = FeedbackContext()
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.feedback_lookback_days)

    # Explicit non-zero ratings — use updated_at so a re-rating counts freshly
    for f in db.query(Feedback).filter(Feedback.rating != 0, Feedback.updated_at >= cutoff).all():
        ctx.signal_rows[f.article_id] = (float(f.rating), f.updated_at, f.reason_tags or [])

    # Implicit signals from read status, skipping explicitly rated articles:
    #   dismissed → −1.0   acknowledged (opened/read) → +ACKNOWLEDGED_SIGNAL
    for rs in db.query(ReadStatus).filter(
        ReadStatus.status.in_(["dismissed", "acknowledged"]),
        ReadStatus.updated_at >= cutoff,
    ).all():
        if rs.article_id in ctx.signal_rows:
            continue
        rating = -1.0 if rs.status == "dismissed" else ACKNOWLEDGED_SIGNAL
        ctx.signal_rows[rs.article_id] = (rating, rs.updated_at, [])

    if ctx.signal_rows:
        ctx.past_articles = (
            db.query(Article).filter(Article.id.in_(ctx.signal_rows.keys())).all()
        )

    ctx.kev_cves = {
        r.cve_id for r in db.query(CVERecord).filter(CVERecord.in_kev == True).all()
    }

    for w in db.query(WatchlistItem).all():
        v = w.value.lower().strip()
        if w.item_type == "actor":
            ctx.watch_actors.add(v)
        elif w.item_type == "cve":
            ctx.watch_cves.add(v)
        else:
            ctx.watch_keywords.add(v)

    return ctx


def _recency_factor(published_at: datetime | None, half_life_days: float) -> float:
    if not published_at:
        return 0.5
    now = datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    age_days = max(0, (now - published_at).total_seconds() / 86400)
    return math.exp(-math.log(2) * age_days / half_life_days)


def _kev_bonus(article: Article, ctx: FeedbackContext) -> float:
    return 1.0 if any(m.cve_id in ctx.kev_cves for m in article.cve_mentions) else 0.0


_QUALITY_TAGS = {"too_vague", "not_actionable"}
_FEATURE_TAG_MAP = {
    "wrong_category": lambda r: r.startswith("category:"),
    "wrong_sector":   lambda r: r == "shared_sector",
    "wrong_actor":    lambda r: r == "shared_actor",
    "wrong_ttp":      lambda r: r.startswith("ttp:"),
    "wrong_geo":      lambda r: r == "shared_geo",
}


def _feedback_signal(
    article: Article,
    ctx: FeedbackContext,
    min_feedback_articles: int,
    decay_half_life_days: float,
) -> tuple[float, list[dict]]:
    """
    Returns (signal_0_to_1, contributing_articles[]).

    Each past signal is weighted by feature overlap (or semantic similarity
    when embeddings exist) and exponential time decay.
    """
    if len(ctx.signal_rows) < min_feedback_articles:
        return 0.0, []

    now = datetime.now(timezone.utc)

    target_category = article.threat_category or ""
    target_ttps = {t.technique_id for t in article.ttp_tags}
    target_actors = {aa.actor_id for aa in article.article_actors}
    target_sectors = set(article.sector_targets or [])
    target_geo = {g.lower() for g in (article.geo_targets or [])}
    target_emb = article.embedding

    contributors = []
    weighted_sum = 0.0
    weight_total = 0.0

    for past in ctx.past_articles:
        rating, ts, reason_tags = ctx.signal_rows[past.id]
        overlap_reasons = []

        if past.threat_category and past.threat_category == target_category:
            overlap_reasons.append(f"category:{target_category}")

        past_ttps = {t.technique_id for t in past.ttp_tags}
        for t in target_ttps & past_ttps:
            overlap_reasons.append(f"ttp:{t}")

        past_actors = {aa.actor_id for aa in past.article_actors}
        if target_actors & past_actors:
            overlap_reasons.append("shared_actor")

        past_sectors = set(past.sector_targets or [])
        if target_sectors & past_sectors:
            overlap_reasons.append("shared_sector")

        past_geo = {g.lower() for g in (past.geo_targets or [])}
        if target_geo & past_geo:
            overlap_reasons.append("shared_geo")

        # Semantic similarity (when both articles have embeddings) catches
        # paraphrased topics the exact-match features miss.
        sim = 0.0
        if target_emb and past.embedding:
            sim = cosine(target_emb, past.embedding)
            if sim >= SEMANTIC_SIM_THRESHOLD:
                overlap_reasons.append(f"semantic:{round(sim, 2)}")

        if not overlap_reasons:
            continue

        # Apply reason tags for negative ratings: filter overlaps to only the
        # tagged dimensions, making penalization more precise.
        if rating < 0 and reason_tags:
            feature_tags = set(reason_tags) - _QUALITY_TAGS
            if feature_tags:
                overlap_reasons = [
                    r for r in overlap_reasons
                    if any(
                        pred(r)
                        for tag, pred in _FEATURE_TAG_MAP.items()
                        if tag in feature_tags
                    )
                ]
                if not overlap_reasons:
                    continue  # tagged dimensions don't overlap — skip signal

        feature_overlap = len(overlap_reasons) / max(len(target_ttps) + 2, 1)
        # Semantic similarity can carry the overlap on its own:
        # rescale [threshold, 1.0] → [0, 1] and take the stronger evidence.
        semantic_overlap = (
            (sim - SEMANTIC_SIM_THRESHOLD) / (1 - SEMANTIC_SIM_THRESHOLD)
            if sim >= SEMANTIC_SIM_THRESHOLD else 0.0
        )
        overlap_score = max(feature_overlap, semantic_overlap)

        # Exponential decay — older feedback weighs less
        ts_aware = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
        age_days = max(0.0, (now - ts_aware).total_seconds() / 86400)
        decay = math.exp(-math.log(2) * age_days / decay_half_life_days)

        eff_weight = overlap_score * decay

        # Quality-only tags: tone down the topic penalty — it's about content,
        # not topic mismatch, so future similar articles shouldn't be hit as hard.
        if rating < 0 and reason_tags and not (set(reason_tags) - _QUALITY_TAGS):
            eff_weight *= 0.25

        weighted_sum += eff_weight * rating
        weight_total += eff_weight

        contributors.append({
            "article_id": past.id,
            "title": past.title,
            "overlap_reasons": overlap_reasons,
            "feedback_rating": rating,
        })

    if weight_total == 0:
        return 0.0, []

    raw_signal = weighted_sum / weight_total
    signal = (raw_signal + 1) / 2  # normalise to [0, 1]

    return round(signal, 4), contributors


def _profile_match(article: Article, profile: UserProfile, ctx: FeedbackContext | None = None) -> float:
    """Average overlap across whichever profile dimensions are non-empty.
    Watchlist hits (pinned actors/CVEs/keywords) force a full relevance match."""
    scores = []

    # Sectors
    p_sectors = {s.lower() for s in (profile.sectors or [])}
    if p_sectors:
        a_sectors = {s.lower() for s in (article.sector_targets or [])}
        scores.append(min(len(a_sectors & p_sectors) / len(p_sectors), 1.0))

    # Threat actors
    p_actors = {a.lower() for a in (profile.threat_actors or [])}
    if p_actors:
        a_actors = {aa.actor.name.lower() for aa in article.article_actors if aa.actor}
        scores.append(min(len(a_actors & p_actors) / len(p_actors), 1.0))

    # Threat categories
    p_cats = {c.lower() for c in (profile.categories or [])}
    if p_cats:
        scores.append(1.0 if (article.threat_category or "").lower() in p_cats else 0.0)

    # Keywords matched against title + summary
    p_kw = [k.lower() for k in (profile.keywords or [])]
    if p_kw:
        text = f"{article.title} {article.ai_summary or ''}".lower()
        hits = sum(1 for kw in p_kw if kw in text)
        scores.append(min(hits / len(p_kw), 1.0))

    # Geo targets — regions the user cares about being targeted
    p_geo_targets = {g.lower() for g in (profile.geo_targets or [])}
    if p_geo_targets:
        a_geo = {g.lower() for g in (article.geo_targets or [])}
        scores.append(min(len(a_geo & p_geo_targets) / len(p_geo_targets), 1.0))

    # Geo origins — threat actor origins the user wants to track
    p_geo_origins = {g.lower() for g in (profile.geo_origins or [])}
    if p_geo_origins:
        a_origin = (article.geo_origin or "").lower()
        scores.append(1.0 if a_origin in p_geo_origins else 0.0)

    base = round(sum(scores) / len(scores), 4) if scores else 0.0

    # Watchlist override
    if ctx and (ctx.watch_actors or ctx.watch_cves or ctx.watch_keywords):
        a_actors = {aa.actor.name.lower() for aa in article.article_actors if aa.actor}
        a_cves = {m.cve_id.lower() for m in article.cve_mentions}
        text = f"{article.title} {article.ai_summary or ''}".lower()
        hit = (
            (a_actors & ctx.watch_actors)
            or (a_cves & ctx.watch_cves)
            or any(kw in text for kw in ctx.watch_keywords)
        )
        if hit:
            return 1.0

    return base


def compute_score(
    db: Session,
    article: Article,
    config: ScoringConfig | None = None,
    profile: UserProfile | None = None,
    ctx: FeedbackContext | None = None,
) -> dict:
    """
    Returns a dict with the full score breakdown ready to store in bulletin_items.
    Pass a prebuilt ctx when scoring many articles — it avoids re-running the
    feedback/KEV/watchlist queries per article.
    """
    if config is None:
        config = _get_config(db)
    if profile is None:
        profile = _get_profile(db)
    if ctx is None:
        ctx = build_feedback_context(db, config)

    raw_sev = (article.ai_severity_score or 0.0) / 100.0
    raw_kev = _kev_bonus(article, ctx)
    raw_rec = _recency_factor(article.published_at, config.recency_half_life_days)
    raw_fb, fb_articles = _feedback_signal(
        article,
        ctx,
        config.min_feedback_articles,
        config.feedback_decay_half_life_days,
    )
    raw_pm = _profile_match(article, profile, ctx)

    score_sev = config.weight_ai_severity * raw_sev
    score_kev = config.weight_kev_bonus * raw_kev
    score_rec = config.weight_recency * raw_rec
    score_fb  = config.weight_feedback_signal * raw_fb
    score_pm  = config.weight_profile_match * raw_pm

    total = round(score_sev + score_fb + score_pm + score_kev + score_rec, 4)

    return {
        "computed_score": total,
        "score_ai_severity":    round(score_sev, 4),
        "score_feedback_signal": round(score_fb, 4),
        "score_profile_match":  round(score_pm, 4),
        "score_kev_bonus":      round(score_kev, 4),
        "score_recency":        round(score_rec, 4),
        "raw_ai_severity":      round(raw_sev, 4),
        "raw_feedback_signal":  round(raw_fb, 4),
        "raw_profile_match":    round(raw_pm, 4),
        "raw_kev_bonus":        round(raw_kev, 4),
        "raw_recency_factor":   round(raw_rec, 4),
        "feedback_signal_articles": fb_articles,
    }
