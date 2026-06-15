from datetime import datetime, timedelta, timezone
from itertools import combinations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models import Article, IOC, CVEMention, CVERecord, ArticleActor, ThreatActor, TTPTag

router = APIRouter(prefix="/entities", tags=["entities"])

MAX_TEXT = 12_000  # chars returned for scraped_text


def _article_ctx(article: Article) -> dict:
    return {
        "id": article.id,
        "title": article.title,
        "url": article.url,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "ai_summary": article.ai_summary,
        "enrichment_status": article.enrichment_status,
        "scraped_text": (article.scraped_text or "")[:MAX_TEXT] if article.scraped_text else None,
        "entities": {
            "iocs": [
                {"id": i.id, "ioc_type": i.ioc_type, "value": i.value}
                for i in article.iocs
            ],
            "cve_mentions": [
                {"id": c.id, "cve_id": c.cve_id}
                for c in article.cve_mentions
            ],
            "actors": [
                {"id": aa.id, "actor_id": aa.actor_id, "name": aa.actor.name if aa.actor else "Unknown"}
                for aa in article.article_actors
            ],
            "ttps": [
                {"id": t.id, "technique_id": t.technique_id, "technique_name": t.technique_name, "tactic": t.tactic}
                for t in article.ttp_tags
            ],
        },
    }


@router.get("/cve/{cve_id:path}")
def cve_context(cve_id: str, db: Session = Depends(get_db)):
    record = db.query(CVERecord).filter(CVERecord.cve_id == cve_id).first()
    mentions = db.query(CVEMention).filter(CVEMention.cve_id == cve_id).all()
    articles = [_article_ctx(m.article) for m in mentions if m.article]
    return {
        "cve_id": cve_id,
        "record": {
            "cvss_score": record.cvss_score,
            "epss_score": record.epss_score,
            "epss_percentile": record.epss_percentile,
            "in_kev": record.in_kev,
            "kev_due_date": record.kev_due_date,
            "nvd_description": record.nvd_description,
            "ai_summary": record.ai_summary,
        } if record else None,
        "articles": articles,
    }


@router.get("/ioc/{ioc_id}")
def ioc_context(ioc_id: str, db: Session = Depends(get_db)):
    ioc = db.query(IOC).filter(IOC.id == ioc_id).first()
    if not ioc:
        raise HTTPException(404, "IOC not found")

    same_value = db.query(IOC).filter(IOC.value == ioc.value, IOC.id != ioc_id).limit(10).all()
    other_article_ids = list({i.article_id for i in same_value})
    other_articles = []
    if other_article_ids:
        other_articles = [
            _article_ctx(a)
            for a in db.query(Article).filter(Article.id.in_(other_article_ids)).all()
        ]

    return {
        "ioc": {
            "id": ioc.id,
            "ioc_type": ioc.ioc_type,
            "value": ioc.value,
            "user_note": ioc.user_note,
        },
        "article": _article_ctx(ioc.article) if ioc.article else None,
        "other_articles": other_articles,
    }


@router.get("/actor/{actor_id}")
def actor_context(actor_id: str, db: Session = Depends(get_db)):
    actor = db.query(ThreatActor).filter(ThreatActor.id == actor_id).first()
    if not actor:
        raise HTTPException(404, "Actor not found")

    articles = [
        _article_ctx(aa.article)
        for aa in actor.article_actors
        if aa.article
    ]
    return {
        "actor": {
            "id": actor.id,
            "name": actor.name,
            "aliases": actor.aliases or [],
        },
        "articles": articles,
    }


@router.get("/graph")
def relationship_graph(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=3650),
    max_articles: int = Query(40, ge=1, le=100),
    evidence_only: bool = False,
    types: str = Query("actor,cve,ioc,ttp,sector,source"),
):
    """Bounded article/entity relationship graph for interactive visualization."""
    enabled = {t.strip() for t in types.split(",") if t.strip()}
    allowed = {"actor", "cve", "ioc", "ttp", "sector", "source"}
    if not enabled <= allowed:
        raise HTTPException(400, f"types must be a comma-separated subset of: {', '.join(sorted(allowed))}")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    articles = (
        db.query(Article)
        .filter(Article.enrichment_status == "enriched", Article.created_at >= cutoff)
        .order_by(Article.published_at.desc(), Article.created_at.desc())
        .limit(max_articles)
        .all()
    )

    nodes = {}
    edges = {}

    def add_node(node_id: str, node_type: str, label: str, **extra):
        nodes.setdefault(node_id, {"id": node_id, "type": node_type, "label": label, **extra})

    def add_edge(left: dict, right: dict, article: Article):
        source, target = sorted((left["id"], right["id"]))
        edge_id = f"{source}|{target}"
        edge = edges.setdefault(edge_id, {
            "id": edge_id,
            "source": source,
            "target": target,
            "relation": "co_occurs",
            "weight": 0,
            "articles": [],
        })
        if any(item["article_id"] == article.id for item in edge["articles"]):
            return
        edge["weight"] += 1
        if len(edge["articles"]) < 10:
            edge["articles"].append({
                "article_id": article.id,
                "title": article.title,
                "published_at": article.published_at.isoformat() if article.published_at else None,
                "evidence": [e for e in (left.get("evidence"), right.get("evidence")) if e],
            })

    for article in articles:
        article_entities = {}

        def add_article_entity(node_id: str, node_type: str, label: str, evidence: str | None = None, **extra):
            add_node(node_id, node_type, label, **extra)
            article_entities.setdefault(node_id, {"id": node_id, "evidence": evidence})

        if "source" in enabled and article.source:
            node_id = f"source:{article.source.id}"
            add_article_entity(node_id, "source", article.source.name)
        if "sector" in enabled:
            for sector in article.sector_targets or []:
                node_id = f"sector:{sector.lower()}"
                add_article_entity(node_id, "sector", sector)
        if "actor" in enabled:
            for association in article.article_actors:
                if evidence_only and not association.source_excerpt:
                    continue
                node_id = f"actor:{association.actor_id}"
                add_article_entity(node_id, "actor", association.actor.name if association.actor else "Unknown", association.source_excerpt, entity_id=association.actor_id)
        if "cve" in enabled:
            for mention in article.cve_mentions:
                if evidence_only and not mention.source_excerpt:
                    continue
                node_id = f"cve:{mention.cve_id}"
                add_article_entity(node_id, "cve", mention.cve_id, mention.source_excerpt, entity_id=mention.cve_id)
        if "ioc" in enabled:
            for ioc in article.iocs:
                if evidence_only and not ioc.source_excerpt:
                    continue
                node_id = f"ioc:{ioc.ioc_type}:{ioc.value}"
                add_article_entity(node_id, "ioc", ioc.value, ioc.source_excerpt, entity_id=ioc.id, subtype=ioc.ioc_type)
        if "ttp" in enabled:
            for ttp in article.ttp_tags:
                if evidence_only and not ttp.source_excerpt:
                    continue
                node_id = f"ttp:{ttp.technique_id}"
                add_article_entity(node_id, "ttp", ttp.technique_id, ttp.source_excerpt, entity_id=ttp.id, detail=ttp.technique_name)

        # Project article membership into direct entity-to-entity relationships.
        # Cap per-article fanout to keep pathological extraction output bounded.
        for left, right in combinations(list(article_entities.values())[:30], 2):
            add_edge(left, right, article)

    edge_list = sorted(edges.values(), key=lambda edge: edge["weight"], reverse=True)[:1000]
    connected = {e["source"] for e in edge_list} | {e["target"] for e in edge_list}
    return {
        "nodes": [node for node_id, node in nodes.items() if node_id in connected],
        "edges": edge_list,
        "meta": {
            "days": days,
            "article_limit": max_articles,
            "article_count": len(articles),
            "projection": "entity_to_entity",
            "evidence_only": evidence_only,
            "types": sorted(enabled),
        },
    }
