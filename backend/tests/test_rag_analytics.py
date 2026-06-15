from datetime import datetime, timezone

from app.models import Article, ArticleActor, CVEMention, Source, ThreatActor
from app.services.rag import _deterministic_query, _retrieve_relationships


def _seed_rag_article(db):
    source = Source(name="RAG source", url="https://rag.test/feed")
    actor = ThreatActor(name="RAG Actor")
    db.add_all([source, actor])
    db.flush()
    article = Article(
        source_id=source.id,
        url="https://rag.test/article",
        url_hash="rag-article",
        title="RAG ransomware article",
        enrichment_status="enriched",
        threat_category="Ransomware",
        published_at=datetime.now(timezone.utc),
        ai_summary="RAG Actor exploited CVE-2026-1234.",
    )
    db.add(article)
    db.flush()
    db.add_all([
        ArticleActor(article_id=article.id, actor_id=actor.id, source_excerpt="RAG Actor conducted the campaign."),
        CVEMention(article_id=article.id, cve_id="CVE-2026-1234", source_excerpt="The campaign exploited CVE-2026-1234."),
    ])
    db.commit()
    return article


def test_deterministic_count_and_timeline(db):
    article = _seed_rag_article(db)

    count = _deterministic_query(db, "How many ransomware articles in the last 30 days?")
    timeline = _deterministic_query(db, "Show a timeline for CVE-2026-1234")

    assert count["kind"] == "count"
    assert count["value"] >= 1
    assert timeline["kind"] == "timeline"
    assert any(item["id"] == article.id for item in timeline["items"])


def test_relationship_retrieval_keeps_evidence(db):
    article = _seed_rag_article(db)

    relationships = _retrieve_relationships(db, "What is related to CVE-2026-1234?")

    assert any(item["article_id"] == article.id and item["type"] == "actor" for item in relationships)
    assert any(item["evidence"] for item in relationships)


def test_deterministic_relationship_count(db):
    _seed_rag_article(db)

    result = _deterministic_query(db, "How many CVEs are associated with RAG Actor?")

    assert result["kind"] == "count"
    assert result["value"] == 1
    assert result["items"]
