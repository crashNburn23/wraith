from app.models import (
    Article, ArticleActor, Bulletin, BulletinItem, CVEMention,
    Source, TTPTag, ThreatActor,
)
from app.services.clustering import cluster_bulletin_items
from uuid import uuid4


def _bulletin_with_articles(db, count=2):
    suffix = uuid4().hex[:8]
    source = Source(name="Cluster source", url=f"https://cluster.test/{suffix}/feed")
    bulletin = Bulletin(bulletin_date=f"test-{suffix}")
    db.add_all([source, bulletin])
    db.flush()
    articles = []
    for index in range(count):
        article = Article(
            source_id=source.id,
            url=f"https://cluster.test/{suffix}/{index}",
            url_hash=f"cluster-{suffix}-{index}",
            title=f"Article {index}",
            enrichment_status="enriched",
        )
        db.add(article)
        db.flush()
        db.add(BulletinItem(bulletin_id=bulletin.id, article_id=article.id, rank=index + 1))
        articles.append(article)
    db.commit()
    db.refresh(bulletin)
    return bulletin, articles


def test_shared_actor_alone_does_not_cluster(db):
    bulletin, articles = _bulletin_with_articles(db)
    actor = ThreatActor(name="Broad Actor")
    db.add(actor)
    db.flush()
    db.add_all([
        ArticleActor(article_id=articles[0].id, actor_id=actor.id),
        ArticleActor(article_id=articles[1].id, actor_id=actor.id),
    ])
    db.commit()

    cluster_bulletin_items(db, bulletin)

    assert all(item.cluster_id is None for item in bulletin.items)


def test_shared_actor_and_ttp_clusters(db):
    bulletin, articles = _bulletin_with_articles(db)
    actor = ThreatActor(name="Specific Actor")
    db.add(actor)
    db.flush()
    for article in articles:
        db.add(ArticleActor(article_id=article.id, actor_id=actor.id))
        db.add(TTPTag(article_id=article.id, technique_id="T1059", technique_name="Command Interpreter"))
    db.commit()

    cluster_bulletin_items(db, bulletin)

    assert bulletin.items[0].cluster_id is not None
    assert bulletin.items[0].cluster_id == bulletin.items[1].cluster_id


def test_shared_cve_clusters(db):
    bulletin, articles = _bulletin_with_articles(db)
    for article in articles:
        db.add(CVEMention(article_id=article.id, cve_id="CVE-2026-12345"))
    db.commit()

    cluster_bulletin_items(db, bulletin)

    assert bulletin.items[0].cluster_id == bulletin.items[1].cluster_id
