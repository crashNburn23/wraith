"""
Saved-search alert runner.

Called after each enrichment batch. Evaluates every alert-enabled saved search
against articles enriched since the last alert, sends a webhook notification if
matches are found, and updates last_alerted_at.
"""
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Article, ThreatActor, ArticleActor, TTPTag, CVEMention
from app.models.ops import SavedSearch

logger = logging.getLogger(__name__)


def _apply_filters(db: Session, filters: dict, since: datetime | None = None):
    query = db.query(Article).filter(Article.enrichment_status == "enriched")

    if since:
        query = query.filter(Article.enriched_at >= since)

    q = filters.get("q", "")
    if q:
        query = query.filter(or_(Article.title.ilike(f"%{q}%"), Article.ai_summary.ilike(f"%{q}%")))

    if filters.get("category"):
        query = query.filter(Article.threat_category == filters["category"])

    sev = filters.get("severity_min")
    if sev is not None:
        query = query.filter(Article.ai_severity_score >= sev)

    if filters.get("actor"):
        actor_obj = db.query(ThreatActor).filter(ThreatActor.name.ilike(f"%{filters['actor']}%")).first()
        if actor_obj:
            ids = [aa.article_id for aa in db.query(ArticleActor).filter(ArticleActor.actor_id == actor_obj.id).all()]
            query = query.filter(Article.id.in_(ids))
        else:
            return query.filter(Article.id.is_(None))  # no matches

    if filters.get("ttp"):
        ids = [t.article_id for t in db.query(TTPTag).filter(TTPTag.technique_id == filters["ttp"]).all()]
        query = query.filter(Article.id.in_(ids))

    if filters.get("cve"):
        ids = [m.article_id for m in db.query(CVEMention).filter(CVEMention.cve_id.ilike(f"%{filters['cve']}%")).all()]
        query = query.filter(Article.id.in_(ids))

    return query


async def _send_webhook(name: str, matches: list[Article]) -> None:
    url = settings.BRIEF_WEBHOOK_URL
    if not url:
        return
    top = matches[:5]
    lines = [f"Wraith alert: {name} — {len(matches)} new match{'es' if len(matches) != 1 else ''}"]
    for a in top:
        sev = int(a.ai_severity_score or 0)
        lines.append(f"  [{sev}] {a.title}")
    if len(matches) > 5:
        lines.append(f"  … and {len(matches) - 5} more")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, content="\n".join(lines).encode(), headers={"Title": "Wraith alert"})
        logger.info("Alert webhook sent for '%s' (%d matches)", name, len(matches))
    except Exception as e:
        logger.warning("Alert webhook failed for '%s': %s", name, e)


async def run_alerts(db: Session) -> int:
    """Evaluate all alert-enabled saved searches. Returns count of searches that fired."""
    searches = db.query(SavedSearch).filter(SavedSearch.alert_enabled == True).all()  # noqa: E712
    if not searches:
        return 0

    fired = 0
    now = datetime.now(timezone.utc)

    for s in searches:
        since = s.last_alerted_at
        filters = s.filters or {}

        # Apply the alert severity threshold on top of the saved filters
        alert_sev = s.alert_severity_min or 0
        effective_filters = {**filters}
        if alert_sev > 0:
            existing_sev = effective_filters.get("severity_min") or 0
            effective_filters["severity_min"] = max(existing_sev, alert_sev)

        query = _apply_filters(db, effective_filters, since=since)
        matches = query.order_by(Article.ai_severity_score.desc()).limit(100).all()

        if matches:
            s.match_count = (s.match_count or 0) + len(matches)
            s.last_alerted_at = now
            db.commit()
            await _send_webhook(s.name, matches)
            fired += 1
        else:
            # Still update last_alerted_at so the next run only looks at articles
            # enriched since now, not since the beginning of time.
            s.last_alerted_at = now
            db.commit()

    logger.info("Alert runner: %d/%d searches fired", fired, len(searches))
    return fired
