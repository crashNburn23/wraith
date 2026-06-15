import logging
from datetime import datetime, timezone, date
from sqlalchemy.orm import Session
from app.models import Article, Bulletin, BulletinItem
from app.services.scoring import compute_score, _get_config, _get_profile, build_feedback_context
from app.core.config import settings

logger = logging.getLogger(__name__)


def build_bulletin(db: Session, for_date: date | None = None, include_all: bool = False) -> Bulletin:
    """
    Build (or rebuild) the bulletin for a date.

    By default only articles that have never appeared in a *previous* bulletin
    are candidates — the bulletin stays genuinely daily instead of re-ranking
    the entire archive. Articles already in today's bulletin stay eligible so
    a rebuild rescores rather than drops them. include_all=True scores the
    whole enriched archive (old behaviour).

    Capped at settings.BULLETIN_MAX_ITEMS.
    """
    if for_date is None:
        for_date = date.today()
    date_str = for_date.isoformat()

    config = _get_config(db)
    profile = _get_profile(db)
    ctx = build_feedback_context(db, config)

    query = db.query(Article).filter(Article.enrichment_status == "enriched")

    if not include_all:
        prior_article_ids = (
            db.query(BulletinItem.article_id)
            .join(Bulletin, Bulletin.id == BulletinItem.bulletin_id)
            .filter(Bulletin.bulletin_date != date_str)
        )
        query = query.filter(~Article.id.in_(prior_article_ids))

    articles = query.all()

    scored = []
    for article in articles:
        breakdown = compute_score(db, article, config, profile, ctx)
        scored.append((article, breakdown))

    scored.sort(key=lambda x: x[1]["computed_score"], reverse=True)
    scored = scored[: settings.BULLETIN_MAX_ITEMS]

    # Upsert bulletin
    bulletin = db.query(Bulletin).filter(Bulletin.bulletin_date == date_str).first()
    if bulletin:
        db.query(BulletinItem).filter(BulletinItem.bulletin_id == bulletin.id).delete()
    else:
        bulletin = Bulletin(bulletin_date=date_str)
        db.add(bulletin)
        db.flush()

    bulletin.generated_at = datetime.now(timezone.utc)

    for rank, (article, breakdown) in enumerate(scored, start=1):
        item = BulletinItem(
            bulletin_id=bulletin.id,
            article_id=article.id,
            rank=rank,
            **breakdown,
        )
        db.add(item)

    db.commit()
    db.refresh(bulletin)

    from app.services.clustering import cluster_bulletin_items, confirm_story_clusters_sync
    cluster_bulletin_items(db, bulletin)
    confirm_story_clusters_sync(bulletin)
    db.commit()

    logger.info(
        "Built bulletin %s with %d items (%d candidates, include_all=%s)",
        date_str, len(scored), len(articles), include_all,
    )
    return bulletin
