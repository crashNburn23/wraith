import re
import logging
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from app.models import Article, IOC, CVEMention, CVERecord, ThreatActor, ArticleActor, TTPTag
from app.services.llm_client import get_llm_client, is_anthropic
from app.services import embeddings
from app.services.prompt_safety import UNTRUSTED_CONTENT_RULE, untrusted_block
from app.core.config import settings

logger = logging.getLogger(__name__)

CVE_PATTERN = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)
IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
DOMAIN_PATTERN = re.compile(r"\b[a-z0-9-]+\.[a-z]{2,}\b", re.IGNORECASE)
TTP_PATTERN = re.compile(r"\bT\d{4}(?:\.\d{3})?\b", re.IGNORECASE)

SEMANTIC_MIN_SIM = 0.35


async def _retrieve_articles_semantic(db: Session, query: str, limit: int = 6) -> list[dict] | None:
    """Embedding-based retrieval. Returns None when embeddings are unavailable
    so the caller falls back to keyword search."""
    if not embeddings.enabled():
        return None
    qvec = await embeddings.embed_text(query)
    if not qvec:
        return None
    rows = (
        db.query(Article.id, Article.title, Article.url, Article.ai_summary, Article.embedding)
        .filter(Article.enrichment_status == "enriched", Article.embedding.isnot(None))
        .all()
    )
    if not rows:
        return None
    scored = sorted(
        ((embeddings.cosine(qvec, r.embedding), r) for r in rows),
        key=lambda x: x[0],
        reverse=True,
    )
    top = [(s, r) for s, r in scored[:limit] if s >= SEMANTIC_MIN_SIM]
    if not top:
        return None
    ids = [r.id for _, r in top]
    articles = {a.id: a for a in db.query(Article).filter(Article.id.in_(ids)).all()}
    return [_article_result(articles[article_id]) for article_id in ids if article_id in articles]


def _retrieve_articles(db: Session, query: str, limit: int = 6) -> list[dict]:
    words = [w for w in re.split(r"\W+", query) if len(w) > 3][:6]
    if not words:
        return []
    conditions = [
        or_(Article.title.ilike(f"%{w}%"), Article.ai_summary.ilike(f"%{w}%"))
        for w in words
    ]
    rows = (
        db.query(Article)
        .filter(Article.enrichment_status == "enriched", or_(*conditions))
        .order_by(Article.ai_severity_score.desc())
        .limit(limit)
        .all()
    )
    return [_article_result(r) for r in rows]


def _article_result(article: Article) -> dict:
    excerpts = []
    for entity in [*article.iocs, *article.cve_mentions, *article.ttp_tags, *article.article_actors]:
        if entity.source_excerpt and entity.source_excerpt not in excerpts:
            excerpts.append(entity.source_excerpt)
    return {
        "id": article.id,
        "title": article.title,
        "url": article.url,
        "summary": article.ai_summary or "",
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "severity": article.ai_severity_score,
        "source": article.source.name if article.source else None,
        "evidence": excerpts[:3],
    }


def _retrieve_iocs(db: Session, query: str) -> list[dict]:
    values = IP_PATTERN.findall(query) + DOMAIN_PATTERN.findall(query)
    if not values:
        return []
    iocs = db.query(IOC).filter(IOC.value.in_(values)).limit(10).all()
    return [{"type": i.ioc_type, "value": i.value, "article_id": i.article_id, "evidence": i.source_excerpt} for i in iocs]


def _retrieve_cves(db: Session, query: str) -> list[dict]:
    cve_ids = CVE_PATTERN.findall(query)
    if not cve_ids:
        return []
    records = db.query(CVERecord).filter(CVERecord.cve_id.in_(cve_ids)).all()
    return [
        {"cve_id": r.cve_id, "cvss": r.cvss_score, "epss": r.epss_score, "in_kev": r.in_kev}
        for r in records
    ]


def _retrieve_actors(db: Session, query: str) -> list[dict]:
    ignored = {
        "what", "which", "show", "many", "count", "number", "related", "associated",
        "linked", "connected", "with", "actor", "actors", "group", "groups", "threat",
        "articles", "timeline", "about", "have", "been",
    }
    words = [w for w in re.split(r"\W+", query) if len(w) > 3 and w.lower() not in ignored]
    if not words:
        return []
    conditions = [ThreatActor.name.ilike(f"%{w}%") for w in words]
    actors = db.query(ThreatActor).filter(or_(*conditions)).limit(5).all()
    return [{"id": a.id, "name": a.name, "aliases": a.aliases} for a in actors]


def _retrieve_relationships(db: Session, query: str, limit: int = 20) -> list[dict]:
    article_ids = set()
    for cve_id in CVE_PATTERN.findall(query):
        article_ids.update(m.article_id for m in db.query(CVEMention).filter(CVEMention.cve_id == cve_id.upper()).all())
    for ttp_id in TTP_PATTERN.findall(query):
        article_ids.update(t.article_id for t in db.query(TTPTag).filter(TTPTag.technique_id == ttp_id.upper()).all())
    for actor in _retrieve_actors(db, query):
        article_ids.update(a.article_id for a in db.query(ArticleActor).filter(ArticleActor.actor_id == actor["id"]).all())
    for ioc in _retrieve_iocs(db, query):
        article_ids.add(ioc["article_id"])
    if not article_ids:
        return []

    relationships = []
    for article in db.query(Article).filter(Article.id.in_(list(article_ids))).limit(10).all():
        entities = (
            [{"type": "actor", "value": aa.actor.name, "evidence": aa.source_excerpt} for aa in article.article_actors if aa.actor]
            + [{"type": "cve", "value": c.cve_id, "evidence": c.source_excerpt} for c in article.cve_mentions]
            + [{"type": "ioc", "value": i.value, "evidence": i.source_excerpt} for i in article.iocs]
            + [{"type": "ttp", "value": t.technique_id, "evidence": t.source_excerpt} for t in article.ttp_tags]
        )
        relationships.extend({
            "article_id": article.id,
            "article_title": article.title,
            **entity,
        } for entity in entities)
    return relationships[:limit]


def _time_cutoff(query: str) -> tuple[datetime | None, str | None]:
    match = re.search(r"(?:last|past)\s+(\d+)\s+(day|week|month)s?", query, re.IGNORECASE)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        days = amount * {"day": 1, "week": 7, "month": 30}[unit]
        return datetime.now(timezone.utc) - timedelta(days=days), f"last {amount} {unit}{'s' if amount != 1 else ''}"
    if re.search(r"\brecent(?:ly)?\b", query, re.IGNORECASE):
        return datetime.now(timezone.utc) - timedelta(days=30), "last 30 days"
    return None, None


def _deterministic_query(db: Session, query: str) -> dict | None:
    lower = query.lower()
    wants_count = bool(re.search(r"\b(how many|count|number of)\b", lower))
    wants_timeline = bool(re.search(r"\b(timeline|chronolog|over time)\b", lower))
    if not wants_count and not wants_timeline:
        return None

    cutoff, window = _time_cutoff(query)
    categories = ["ransomware", "malware", "phishing", "vulnerability", "apt", "data breach", "ddos", "supply chain"]
    category = next((value for value in categories if value in lower), None)
    entity_models = [
        (r"\biocs?\b|\bindicators?\b", IOC, IOC.value, "unique IOCs"),
        (r"\bcves?\b|\bvulnerabilities\b", CVEMention, CVEMention.cve_id, "unique CVEs"),
        (r"\bactors?\b|\bthreat groups?\b", ThreatActor, ThreatActor.id, "threat actors"),
        (r"\bttps?\b|\btechniques?\b", TTPTag, TTPTag.technique_id, "unique TTPs"),
    ]
    if wants_count and re.search(r"\b(related|associated|linked|connected)\b", lower):
        relationships = _retrieve_relationships(db, query, limit=200)
        target_patterns = [
            (r"\biocs?\b|\bindicators?\b", "ioc", "unique related IOCs"),
            (r"\bcves?\b|\bvulnerabilities\b", "cve", "unique related CVEs"),
            (r"\bactors?\b|\bthreat groups?\b", "actor", "related threat actors"),
            (r"\bttps?\b|\btechniques?\b", "ttp", "unique related TTPs"),
        ]
        for pattern, entity_type, label in target_patterns:
            if re.search(pattern, lower):
                matching = [item for item in relationships if item["type"] == entity_type]
                value = len({item["value"] for item in matching})
                article_ids = list(dict.fromkeys(item["article_id"] for item in matching))[:10]
                articles = db.query(Article).filter(Article.id.in_(article_ids)).all() if article_ids else []
                return {
                    "kind": "count",
                    "text": f"There are {value} {label} in the matching relationship evidence.",
                    "value": value,
                    "items": [_article_result(article) for article in articles],
                }

    if wants_count and "article" not in lower:
        for pattern, model, distinct_column, label in entity_models:
            if re.search(pattern, lower):
                count_query = db.query(func.count(func.distinct(distinct_column)))
                if cutoff or category:
                    if model is ThreatActor:
                        count_query = count_query.join(ArticleActor, ArticleActor.actor_id == ThreatActor.id).join(
                            Article, Article.id == ArticleActor.article_id
                        )
                    else:
                        count_query = count_query.join(Article, Article.id == model.article_id)
                    count_query = count_query.filter(Article.enrichment_status == "enriched")
                    if cutoff:
                        count_query = count_query.filter(func.coalesce(Article.published_at, Article.created_at) >= cutoff)
                    if category:
                        count_query = count_query.filter(Article.threat_category.ilike(category))
                value = count_query.scalar() or 0
                qualifiers = [category, window]
                scope = f" for {' during the '.join(q for q in qualifiers if q)}" if any(qualifiers) else ""
                return {"kind": "count", "text": f"There are {value} {label}{scope}.", "value": value, "items": []}

    article_query = db.query(Article).filter(Article.enrichment_status == "enriched")
    if cutoff:
        article_query = article_query.filter(func.coalesce(Article.published_at, Article.created_at) >= cutoff)

    cves = [value.upper() for value in CVE_PATTERN.findall(query)]
    ttps = [value.upper() for value in TTP_PATTERN.findall(query)]
    actors = _retrieve_actors(db, query)
    if cves:
        ids = [m.article_id for m in db.query(CVEMention).filter(CVEMention.cve_id.in_(cves)).all()]
        article_query = article_query.filter(Article.id.in_(ids))
    if ttps:
        ids = [t.article_id for t in db.query(TTPTag).filter(TTPTag.technique_id.in_(ttps)).all()]
        article_query = article_query.filter(Article.id.in_(ids))
    if actors:
        actor_ids = [a["id"] for a in actors]
        ids = [a.article_id for a in db.query(ArticleActor).filter(ArticleActor.actor_id.in_(actor_ids)).all()]
        article_query = article_query.filter(Article.id.in_(ids))

    if category:
        article_query = article_query.filter(Article.threat_category.ilike(category))

    rows = article_query.order_by(func.coalesce(Article.published_at, Article.created_at).asc()).all()
    qualifier = ", ".join(cves + ttps + [a["name"] for a in actors] + ([category] if category else [])) or "all enriched intelligence"
    scope = f" during the {window}" if window else ""
    if wants_timeline:
        citations = [_article_result(article) for article in rows[-20:]]
        text = f"Found {len(rows)} matching articles for {qualifier}{scope}. The timeline below is ordered oldest to newest."
        return {"kind": "timeline", "text": text, "value": len(rows), "items": citations}
    return {"kind": "count", "text": f"There are {len(rows)} matching articles for {qualifier}{scope}.", "value": len(rows), "items": [_article_result(a) for a in rows[-10:]]}


def _build_context(articles, iocs, cves, actors, relationships=()) -> str:
    parts = []
    if articles:
        parts.append("RELEVANT ARTICLES:\n" + "\n".join(
            f"- [A{i}] {a['title']}: {a['summary']} Evidence: {' | '.join(a.get('evidence', [])) or 'none'}"
            for i, a in enumerate(articles, 1)
        ))
    if cves:
        parts.append("CVE DATA:\n" + "\n".join(
            f"- {c['cve_id']} CVSS:{c['cvss']} EPSS:{c['epss']} KEV:{c['in_kev']}"
            for c in cves
        ))
    if iocs:
        parts.append("MATCHING IOCs:\n" + "\n".join(
            f"- {i['type']}: {i['value']}" for i in iocs
        ))
    if actors:
        parts.append("THREAT ACTORS:\n" + "\n".join(
            f"- {a['name']}" + (f" (aka {', '.join(a['aliases'])})" if a.get("aliases") else "")
            for a in actors
        ))
    if relationships:
        parts.append("ENTITY RELATIONSHIPS:\n" + "\n".join(
            f"- [{r['article_title']}] contains {r['type']} {r['value']}"
            + (f"; evidence: {r['evidence']}" if r.get("evidence") else "")
            for r in relationships
        ))
    context = "\n\n".join(parts) or "No relevant context found in the database."
    return untrusted_block("retrieved_intel_context", context)


async def stream_chat(
    db: Session,
    messages: list[dict],
) -> AsyncIterator[dict]:
    # Use the last user message for retrieval
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    deterministic = _deterministic_query(db, last_user)
    if deterministic:
        yield {"type": "results", "deterministic": deterministic, "citations": deterministic["items"], "relationships": []}
        yield {"type": "text", "text": deterministic["text"]}
        return
    if settings.LLM_PROVIDER == "anthropic" and not settings.ANTHROPIC_API_KEY:
        yield {"type": "text", "text": "No LLM configured. Set ANTHROPIC_API_KEY or switch to LLM_PROVIDER=ollama."}
        return

    # Semantic retrieval when embeddings are available; keyword fallback otherwise
    articles = await _retrieve_articles_semantic(db, last_user)
    if articles is None:
        articles = _retrieve_articles(db, last_user)
    iocs = _retrieve_iocs(db, last_user)
    cves = _retrieve_cves(db, last_user)
    actors = _retrieve_actors(db, last_user)
    relationships = _retrieve_relationships(db, last_user)
    relationship_article_ids = list(dict.fromkeys(item["article_id"] for item in relationships))
    existing_article_ids = {article["id"] for article in articles}
    if relationship_article_ids:
        related_articles = db.query(Article).filter(Article.id.in_(relationship_article_ids)).all()
        articles.extend(_article_result(article) for article in related_articles if article.id not in existing_article_ids)
        articles = articles[:10]
    context = _build_context(articles, iocs, cves, actors, relationships)
    yield {
        "type": "results",
        "deterministic": None,
        "citations": articles,
        "relationships": relationships,
    }

    system = f"""You are a cybersecurity threat intelligence assistant.
{UNTRUSTED_CONTENT_RULE}
Answer questions about threats, IOCs, CVEs, and threat actors based on the intel database context below.
Be concise and precise. Cite sources using their exact citation IDs such as [A1].
If the context doesn't cover the question, say so rather than hallucinating.

INTEL DATABASE CONTEXT:
{context}"""

    history = [{"role": m["role"], "content": m["content"]} for m in messages[-10:]]
    client = get_llm_client()

    try:
        if is_anthropic():
            async with client.messages.stream(
                model=settings.LLM_MODEL,
                max_tokens=1500,
                system=system,
                messages=history,
            ) as stream:
                async for text in stream.text_stream:
                    yield {"type": "text", "text": text}
        else:
            import httpx
            stream = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                max_tokens=1500,
                stream=True,
                messages=[{"role": "system", "content": system}, *history],
                timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0),
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield {"type": "text", "text": delta}
    except Exception as e:
        logger.error("Chat LLM error: %s", e)
        yield {"type": "text", "text": f"\n\n[Error: {e}]"}
