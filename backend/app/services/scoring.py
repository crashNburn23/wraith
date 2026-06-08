"""
Recommended score for bulletin items — two-axis model.

  Threat axis:    w_sev  × ai_severity/100  +  w_kev × kev_bonus
  Relevance axis: w_fb   × feedback_signal  +  w_profile × profile_match  +  w_rec × recency

All weights read from scoring_config; must sum to 1.0.
"""
import math
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.models import Article, Feedback, ReadStatus, CVEMention, CVERecord, ScoringConfig, UserProfile

logger = logging.getLogger(__name__)


def _get_config(db: Session) -> ScoringConfig:
    cfg = db.query(ScoringConfig).first()
    if not cfg:
        cfg = ScoringConfig()
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def _recency_factor(published_at: datetime | None, half_life_days: float) -> float:
    if not published_at:
        return 0.5
    now = datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    age_days = max(0, (now - published_at).total_seconds() / 86400)
    return math.exp(-math.log(2) * age_days / half_life_days)


def _kev_bonus(db: Session, article: Article) -> float:
    cve_ids = [m.cve_id for m in article.cve_mentions]
    if not cve_ids:
        return 0.0
    kev_count = (
        db.query(CVERecord)
        .filter(CVERecord.cve_id.in_(cve_ids), CVERecord.in_kev == True)
        .count()
    )
    return 1.0 if kev_count > 0 else 0.0


def _feedback_signal(
    db: Session,
    article: Article,
    lookback_days: int,
    min_feedback_articles: int,
    decay_half_life_days: float,
) -> tuple[float, list[dict]]:
    """
    Returns (signal_0_to_1, contributing_articles[])

    Combines explicit ratings (👍/👎) and implicit dismissed signals.
    Each signal is weighted by feature overlap and exponential time decay.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    now = datetime.now(timezone.utc)

    # Explicit non-zero ratings — use updated_at so a re-rating counts freshly
    past_feedback = (
        db.query(Feedback)
        .filter(Feedback.rating != 0, Feedback.updated_at >= cutoff)
        .all()
    )
    # article_id -> (rating, timestamp, reason_tags)
    explicit_map: dict[str, tuple[int, datetime, list]] = {
        f.article_id: (f.rating, f.updated_at, f.reason_tags or []) for f in past_feedback
    }

    # Dismissed articles = implicit -1, skip any already explicitly rated
    dismissed_q = db.query(ReadStatus).filter(
        ReadStatus.status == "dismissed",
        ReadStatus.updated_at >= cutoff,
    )
    if explicit_map:
        dismissed_q = dismissed_q.filter(
            ~ReadStatus.article_id.in_(list(explicit_map.keys()))
        )
    dismissed = dismissed_q.all()

    # Merge: dismissed articles carry no reason_tags (implicit signal)
    signal_rows: dict[str, tuple[int, datetime, list]] = dict(explicit_map)
    for d in dismissed:
        signal_rows[d.article_id] = (-1, d.updated_at, [])

    if len(signal_rows) < min_feedback_articles:
        return 0.0, []

    past_articles = db.query(Article).filter(Article.id.in_(signal_rows.keys())).all()

    target_category = article.threat_category or ""
    target_ttps = {t.technique_id for t in article.ttp_tags}
    target_actors = {aa.actor_id for aa in article.article_actors}
    target_sectors = set(article.sector_targets or [])

    contributors = []
    weighted_sum = 0.0
    weight_total = 0.0

    _QUALITY_TAGS = {"too_vague", "not_actionable"}
    _FEATURE_TAG_MAP = {
        "wrong_category": lambda r: r.startswith("category:"),
        "wrong_sector":   lambda r: r == "shared_sector",
        "wrong_actor":    lambda r: r == "shared_actor",
        "wrong_ttp":      lambda r: r.startswith("ttp:"),
    }

    for past in past_articles:
        rating, ts, reason_tags = signal_rows[past.id]
        overlap_reasons = []

        if past.threat_category and past.threat_category == target_category:
            overlap_reasons.append(f"category:{target_category}")

        past_ttps = {t.technique_id for t in past.ttp_tags}
        shared_ttps = target_ttps & past_ttps
        for t in shared_ttps:
            overlap_reasons.append(f"ttp:{t}")

        past_actors = {aa.actor_id for aa in past.article_actors}
        if target_actors & past_actors:
            overlap_reasons.append("shared_actor")

        past_sectors = set(past.sector_targets or [])
        if target_sectors & past_sectors:
            overlap_reasons.append("shared_sector")

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

        overlap_score = len(overlap_reasons) / max(len(target_ttps) + 2, 1)

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


def _get_profile(db: Session) -> UserProfile:
    p = db.query(UserProfile).filter(UserProfile.id == 1).first()
    if not p:
        p = UserProfile(id=1, sectors=[], threat_actors=[], categories=[], keywords=[])
        db.add(p)
        db.commit()
        db.refresh(p)
    return p


def _profile_match(article: Article, profile: UserProfile) -> float:
    """Average overlap across whichever profile dimensions are non-empty."""
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

    return round(sum(scores) / len(scores), 4) if scores else 0.0


def compute_score(
    db: Session,
    article: Article,
    config: ScoringConfig | None = None,
    profile: UserProfile | None = None,
) -> dict:
    """
    Returns a dict with the full score breakdown ready to store in bulletin_items.
    """
    if config is None:
        config = _get_config(db)
    if profile is None:
        profile = _get_profile(db)

    raw_sev = (article.ai_severity_score or 0.0) / 100.0
    raw_kev = _kev_bonus(db, article)
    raw_rec = _recency_factor(article.published_at, config.recency_half_life_days)
    raw_fb, fb_articles = _feedback_signal(
        db,
        article,
        config.feedback_lookback_days,
        config.min_feedback_articles,
        config.feedback_decay_half_life_days,
    )
    raw_pm = _profile_match(article, profile)

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
