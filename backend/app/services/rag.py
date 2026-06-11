import re
import logging
from typing import AsyncIterator
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models import Article, IOC, CVERecord, ThreatActor
from app.services.llm_client import get_llm_client, is_anthropic
from app.services import embeddings
from app.core.config import settings

logger = logging.getLogger(__name__)

CVE_PATTERN = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)
IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
DOMAIN_PATTERN = re.compile(r"\b[a-z0-9-]+\.[a-z]{2,}\b", re.IGNORECASE)

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
    return [
        {"id": r.id, "title": r.title, "url": r.url, "summary": r.ai_summary or ""}
        for _, r in top
    ]


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
    return [{"id": r.id, "title": r.title, "url": r.url, "summary": r.ai_summary or ""} for r in rows]


def _retrieve_iocs(db: Session, query: str) -> list[dict]:
    iocs = db.query(IOC).filter(IOC.value.ilike(f"%{query.strip()}%")).limit(5).all()
    return [{"type": i.ioc_type, "value": i.value, "article_id": i.article_id} for i in iocs]


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
    words = [w for w in re.split(r"\W+", query) if len(w) > 3]
    if not words:
        return []
    conditions = [ThreatActor.name.ilike(f"%{w}%") for w in words]
    actors = db.query(ThreatActor).filter(or_(*conditions)).limit(5).all()
    return [{"name": a.name, "aliases": a.aliases} for a in actors]


def _build_context(articles, iocs, cves, actors) -> str:
    parts = []
    if articles:
        parts.append("RELEVANT ARTICLES:\n" + "\n".join(
            f"- [{a['title']}]: {a['summary']}" for a in articles
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
    return "\n\n".join(parts) or "No relevant context found in the database."


async def stream_chat(
    db: Session,
    messages: list[dict],
) -> AsyncIterator[str]:
    if settings.LLM_PROVIDER == "anthropic" and not settings.ANTHROPIC_API_KEY:
        yield "No LLM configured. Set ANTHROPIC_API_KEY or switch to LLM_PROVIDER=ollama."
        return

    # Use the last user message for retrieval
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

    # Semantic retrieval when embeddings are available; keyword fallback otherwise
    articles = await _retrieve_articles_semantic(db, last_user)
    if articles is None:
        articles = _retrieve_articles(db, last_user)
    iocs = _retrieve_iocs(db, last_user)
    cves = _retrieve_cves(db, last_user)
    actors = _retrieve_actors(db, last_user)
    context = _build_context(articles, iocs, cves, actors)

    system = f"""You are a cybersecurity threat intelligence assistant.
Answer questions about threats, IOCs, CVEs, and threat actors based on the intel database context below.
Be concise and precise. Cite article titles when referencing specific intelligence.
If the context doesn't cover the question, say so rather than hallucinating.

INTEL DATABASE CONTEXT:
{context}"""

    history = messages[-10:]  # last 10 turns
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
                    yield text
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
                    yield delta
    except Exception as e:
        logger.error("Chat LLM error: %s", e)
        yield f"\n\n[Error: {e}]"
