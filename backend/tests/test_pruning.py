from datetime import datetime, timedelta, timezone

from app.models import Article, Bulletin, BulletinItem, IOC, Source
from app.services.pruning import prune


def _old(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def test_prune_deletes_dependents_through_orm_cascades(db):
    source = Source(name="Prune source", url="https://prune.test/feed")
    db.add(source)
    db.flush()
    article = Article(
        source_id=source.id,
        url="https://prune.test/old",
        url_hash="prune-old",
        title="Old no-text article",
        enrichment_status="no_text",
    )
    db.add(article)
    db.flush()
    db.add(IOC(article_id=article.id, ioc_type="domain", value="evil-prune.test"))
    db.commit()
    article.created_at = _old(20)
    db.commit()

    counts = prune(db)

    assert counts["deleted_error_articles"] == 1
    assert db.get(Article, article.id) is None
    assert db.query(IOC).filter(IOC.article_id == article.id).count() == 0


def test_prune_never_deletes_articles_referenced_by_bulletins(db):
    source = Source(name="Protected source", url="https://protected.test/feed")
    db.add(source)
    db.flush()
    article = Article(
        source_id=source.id,
        url="https://protected.test/old",
        url_hash="protected-old",
        title="Protected old article",
        enrichment_status="no_text",
    )
    bulletin = Bulletin(bulletin_date="2000-01-01")
    db.add_all([article, bulletin])
    db.flush()
    db.add(BulletinItem(bulletin_id=bulletin.id, article_id=article.id, rank=1))
    db.commit()
    article.created_at = _old(20)
    db.commit()

    counts = prune(db)

    assert counts["deleted_error_articles"] == 0
    assert db.get(Article, article.id) is not None
