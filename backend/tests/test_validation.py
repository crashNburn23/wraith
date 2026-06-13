import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routers.enrich import EntityPatch, patch_entity
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
