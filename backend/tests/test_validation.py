import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routers.enrich import EntityPatch, patch_entity
from app.api.routers.entities import relationship_graph
from app.models import Article, CVEMention, Source, TTPTag, ThreatActor, ArticleActor
from app.schemas.scoring import ScoringConfigUpdate


@pytest.mark.parametrize("field", ["recency_half_life_days", "feedback_decay_half_life_days"])
def test_scoring_rejects_non_positive_half_lives(field):
    with pytest.raises(ValidationError):
        ScoringConfigUpdate(**{field: 0})


def test_scoring_rejects_negative_weights():
    with pytest.raises(ValidationError):
        ScoringConfigUpdate(weight_ai_severity=-0.1)


def test_entity_patch_validates_and_normalises_ids(db):
    source = Source(name="Entity source", url="https://entity.test/feed")
    db.add(source)
    db.flush()
    article = Article(
        source_id=source.id,
        url="https://entity.test/article",
        url_hash="entity-article",
        title="Entity article",
    )
    db.add(article)
    db.flush()
    ttp = TTPTag(article_id=article.id, technique_id="T1566", technique_name="Phishing")
    cve = CVEMention(article_id=article.id, cve_id="CVE-2024-1234")
    db.add_all([ttp, cve])
    db.commit()

    patch_entity("ttp", ttp.id, EntityPatch(value="t1059.003"), db)
    patch_entity("cve", cve.id, EntityPatch(value="cve-2025-12345"), db)

    assert ttp.technique_id == "T1059.003"
    assert cve.cve_id == "CVE-2025-12345"
    with pytest.raises(HTTPException):
        patch_entity("ttp", ttp.id, EntityPatch(value="T1059 · Command"), db)


def test_entity_patch_rejects_actor_rename(db):
    source = Source(name="Actor source", url="https://actor.test/feed")
    db.add(source)
    db.flush()
    article = Article(
        source_id=source.id,
        url="https://actor.test/article",
        url_hash="actor-article",
        title="Actor article",
    )
    actor = ThreatActor(name="Original Actor")
    db.add_all([article, actor])
    db.flush()
    association = ArticleActor(article_id=article.id, actor_id=actor.id)
    db.add(association)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        patch_entity("actor", association.id, EntityPatch(value="Renamed Actor"), db)

    assert exc.value.status_code == 400
    assert actor.name == "Original Actor"


def test_relationship_graph_projects_entities_with_article_provenance(db):
    source = Source(name="Graph source", url="https://graph.test/feed")
    actor = ThreatActor(name="Graph Actor")
    db.add_all([source, actor])
    db.flush()
    article = Article(
        source_id=source.id,
        url="https://graph.test/article",
        url_hash="graph-article",
        title="Graph article",
        enrichment_status="enriched",
    )
    db.add(article)
    db.flush()
    db.add_all([
        ArticleActor(article_id=article.id, actor_id=actor.id, source_excerpt="Graph Actor used the flaw."),
        CVEMention(article_id=article.id, cve_id="CVE-2026-9999", source_excerpt="The flaw is CVE-2026-9999."),
    ])
    db.commit()

    graph = relationship_graph(db=db, days=30, max_articles=10, evidence_only=False, types="actor,cve")

    assert {node["type"] for node in graph["nodes"]} == {"actor", "cve"}
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["weight"] == 1
    assert graph["edges"][0]["articles"][0]["article_id"] == article.id
    assert graph["meta"]["projection"] == "entity_to_entity"
