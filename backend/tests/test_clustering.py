from app.models import (
    Article, ArticleActor, Bulletin, BulletinItem, CVEMention,
    Source, TTPTag, ThreatActor,
)
import pytest

from app.services.clustering import cluster_bulletin_items, confirm_story_clusters
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


@pytest.mark.parametrize("response", ['{"same_story": true}', '```json\n{"same_story": true}\n```'])
async def test_llm_confirmation_keeps_confirmed_cluster(db, monkeypatch, response):
    bulletin, articles = _bulletin_with_articles(db)
    for article in articles:
        db.add(CVEMention(article_id=article.id, cve_id="CVE-2026-12345"))
    db.commit()
    cluster_bulletin_items(db, bulletin)

    calls = []

    async def fake_complete(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return response

    monkeypatch.setattr("app.services.clustering.llm_complete", fake_complete)
    await confirm_story_clusters(bulletin)

    assert len(calls) == 1
    assert "UNTRUSTED_DATA" in calls[0][0]
    assert bulletin.items[0].cluster_id == bulletin.items[1].cluster_id


async def test_llm_confirmation_dissolves_rejected_cluster(db, monkeypatch):
    bulletin, articles = _bulletin_with_articles(db)
    for article in articles:
        db.add(CVEMention(article_id=article.id, cve_id="CVE-2026-12345"))
    db.commit()
    cluster_bulletin_items(db, bulletin)

    async def fake_complete(*args, **kwargs):
        return '{"same_story": false}'

    monkeypatch.setattr("app.services.clustering.llm_complete", fake_complete)
    await confirm_story_clusters(bulletin)

    assert all(item.cluster_id is None for item in bulletin.items)
    assert all(item.cluster_size == 1 for item in bulletin.items)
    assert all(item.is_cluster_lead for item in bulletin.items)


async def test_llm_confirmation_skips_singletons(db, monkeypatch):
    bulletin, _ = _bulletin_with_articles(db)
    calls = 0

    async def fake_complete(*args, **kwargs):
        nonlocal calls
        calls += 1
        return '{"same_story": true}'

    monkeypatch.setattr("app.services.clustering.llm_complete", fake_complete)
    await confirm_story_clusters(bulletin)

    assert calls == 0


async def test_llm_confirmation_can_be_disabled(db, monkeypatch):
    bulletin, articles = _bulletin_with_articles(db)
    for article in articles:
        db.add(CVEMention(article_id=article.id, cve_id="CVE-2026-12345"))
    db.commit()
    cluster_bulletin_items(db, bulletin)
    calls = 0

    async def fake_complete(*args, **kwargs):
        nonlocal calls
        calls += 1
        return '{"same_story": false}'

    monkeypatch.setattr("app.services.clustering.settings.LLM_CONFIRM_STORY_CLUSTERS", False)
    monkeypatch.setattr("app.services.clustering.llm_complete", fake_complete)
    await confirm_story_clusters(bulletin)

    assert calls == 0
    assert bulletin.items[0].cluster_id == bulletin.items[1].cluster_id


@pytest.mark.parametrize("response", ["not json", '{"same_story": "yes"}'])
async def test_llm_confirmation_fails_open(db, monkeypatch, response):
    bulletin, articles = _bulletin_with_articles(db)
    for article in articles:
        db.add(CVEMention(article_id=article.id, cve_id="CVE-2026-12345"))
    db.commit()
    cluster_bulletin_items(db, bulletin)
    original_cluster_id = bulletin.items[0].cluster_id

    async def fake_complete(*args, **kwargs):
        return response

    monkeypatch.setattr("app.services.clustering.llm_complete", fake_complete)
    await confirm_story_clusters(bulletin)

    assert bulletin.items[0].cluster_id == original_cluster_id
    assert bulletin.items[1].cluster_id == original_cluster_id
