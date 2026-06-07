"""
Data retention policy (runs weekly via scheduler):

  - scraped_text on enriched articles > 30 days: null it (keep for article text view + re-enrichment)
  - error/no_text articles > 14 days:   delete row — no intelligence, no text
  - pending articles > 30 days:         delete row — feed churn, never processed
  - enriched articles not in any bulletin, > 90 days: delete row
    (bulletin_items, feedback, IOCs, TTPs are cascaded or already orphaned)

  Kept forever: bulletins, bulletin_items, feedback, scoring_config,
                cve_records, threat_actors, sources
"""
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_, not_, exists
from app.models import Article, BulletinItem

logger = logging.getLogger(__name__)


def prune(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    counts = {}

    # 1. Null scraped_text on enriched articles older than 30 days
    cutoff_text = now - timedelta(days=30)
    updated = (
        db.query(Article)
        .filter(
            Article.enrichment_status == "enriched",
            Article.scraped_text.isnot(None),
            Article.enriched_at < cutoff_text,
        )
        .all()
    )
    for a in updated:
        a.scraped_text = None
    counts["scraped_text_freed"] = len(updated)

    # 2. Delete error/no_text articles older than 14 days
    cutoff_14 = now - timedelta(days=14)
    q = db.query(Article).filter(
        Article.enrichment_status.in_(["error", "no_text"]),
        Article.created_at < cutoff_14,
    )
    counts["deleted_error_articles"] = q.count()
    q.delete(synchronize_session=False)

    # 3. Delete pending articles older than 30 days
    cutoff_30 = now - timedelta(days=30)
    q = db.query(Article).filter(
        Article.enrichment_status == "pending",
        Article.created_at < cutoff_30,
    )
    counts["deleted_stale_pending"] = q.count()
    q.delete(synchronize_session=False)

    # 4. Delete enriched articles not in any bulletin, older than 90 days
    cutoff_90 = now - timedelta(days=90)
    in_bulletin = exists().where(BulletinItem.article_id == Article.id)
    q = db.query(Article).filter(
        Article.enrichment_status == "enriched",
        Article.enriched_at < cutoff_90,
        not_(in_bulletin),
    )
    counts["deleted_old_unbulleted"] = q.count()
    q.delete(synchronize_session=False)

    db.commit()
    logger.info("Pruning complete: %s", counts)
    return counts
