import asyncio
import logging
from datetime import datetime, timezone, date
from sqlalchemy.orm import Session
from app.models import Article, Bulletin, BulletinItem
from app.services.scoring import compute_score, _get_config, _get_profile

logger = logging.getLogger(__name__)


def build_bulletin(db: Session, for_date: date | None = None) -> Bulletin:
    if for_date is None:
        for_date = date.today()
    date_str = for_date.isoformat()

    config = _get_config(db)
    profile = _get_profile(db)

    # Get all enriched articles — score them all, sort, take top 30
    articles = (
        db.query(Article)
        .filter(Article.enrichment_status == "enriched")
        .all()
    )

    scored = []
    for article in articles:
        breakdown = compute_score(db, article, config, profile)
        scored.append((article, breakdown))

    scored.sort(key=lambda x: x[1]["computed_score"], reverse=True)

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
    logger.info("Built bulletin %s with %d items", date_str, len(scored))

    # Auto-generate the daily brief after scoring
    try:
        from app.services.brief import generate_brief
        asyncio.run(generate_brief(db, for_date))
    except Exception as e:
        logger.warning("Brief auto-generation failed after bulletin build: %s", e)

    return bulletin
