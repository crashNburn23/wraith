"""
Story clustering: group bulletin items that cover the same incident.

Strategy (applied with Union-Find, most reliable first):
  1. CVE overlap  — articles sharing any CVE are almost certainly the same story.
  2. Multi-entity overlap — articles sharing an actor plus another strong entity.
  3. Embedding similarity — articles with cosine ≥ SIMILARITY_THRESHOLD are merged
     when EMBEDDING_MODEL is configured (embeddings stored at enrichment time).

After grouping, the highest-ranked (lowest rank number) article in each cluster
becomes the lead. Candidate clusters are then confirmed by the LLM. Singletons
get cluster_id=None so the UI can skip them cleanly.
"""
import asyncio
import json
import logging
from collections import Counter
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.bulletin import Bulletin, BulletinItem
from app.services.llm_client import llm_complete
from app.services.prompt_safety import UNTRUSTED_CONTENT_RULE, untrusted_block

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.80
CLUSTER_CONFIRMATION_SYSTEM_PROMPT = f"""You confirm whether cybersecurity news articles cover the same story.
{UNTRUSTED_CONTENT_RULE}

Return only JSON with exactly one boolean key: {{"same_story": true}} or {{"same_story": false}}.

same_story=true only when every article covers the same specific incident, campaign, vulnerability disclosure,
or report. Shared threat actors, techniques, products, or broad themes alone are not enough."""


def _find(parent: dict, x: str) -> str:
    while parent[x] != x:
        parent[x] = parent[parent[x]]  # path compression
        x = parent[x]
    return x


def _union(parent: dict, x: str, y: str) -> None:
    parent[_find(parent, x)] = _find(parent, y)


def cluster_bulletin_items(db: Session, bulletin: Bulletin) -> None:
    """Assign cluster_id, is_cluster_lead, cluster_size to all items in-place.
    Caller must db.commit() afterwards.
    """
    items = bulletin.items
    if not items:
        return

    ids = [item.article_id for item in items]
    parent = {aid: aid for aid in ids}

    cves: dict[str, set] = {}
    actors: dict[str, set] = {}
    ttps: dict[str, set] = {}
    emb: dict[str, list | None] = {}

    for item in items:
        a = item.article
        cves[a.id] = {m.cve_id for m in a.cve_mentions}
        actors[a.id] = {aa.actor_id for aa in a.article_actors}
        ttps[a.id] = {t.technique_id for t in a.ttp_tags}
        emb[a.id] = a.embedding

    # Entity overlap: a CVE match is strong enough alone. Actor overlap is too
    # broad, so require it alongside a shared ATT&CK technique.
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            if cves[a] & cves[b]:
                _union(parent, a, b)
            elif actors[a] & actors[b] and ttps[a] & ttps[b]:
                _union(parent, a, b)

    # 3: embedding similarity (only when enabled and embeddings present)
    from app.services import embeddings as emb_svc
    if emb_svc.enabled():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                if _find(parent, a) == _find(parent, b):
                    continue
                ea, eb = emb[a], emb[b]
                if ea and eb and emb_svc.cosine(ea, eb) >= SIMILARITY_THRESHOLD:
                    _union(parent, a, b)

    root_sizes = Counter(_find(parent, aid) for aid in ids)
    root_to_uuid: dict[str, str] = {
        root: str(uuid4())
        for root, count in root_sizes.items()
        if count > 1
    }

    # Lead = first (lowest rank number) item encountered per cluster
    cluster_leads: dict[str, BulletinItem] = {}
    for item in sorted(items, key=lambda i: i.rank):
        root = _find(parent, item.article_id)
        cid = root_to_uuid.get(root)
        item.cluster_id = cid
        item.cluster_size = root_sizes[root]
        if cid and cid not in cluster_leads:
            cluster_leads[cid] = item

    for item in items:
        if item.cluster_id:
            item.is_cluster_lead = cluster_leads[item.cluster_id].id == item.id
        else:
            item.is_cluster_lead = True

    n_clustered = sum(1 for item in items if item.cluster_id)
    logger.info(
        "Clustered bulletin %s: %d items → %d clusters, %d singletons",
        bulletin.bulletin_date,
        len(items),
        len(root_to_uuid),
        len(items) - n_clustered,
    )


def _confirmation_prompt(items: list[BulletinItem]) -> str:
    blocks = []
    for index, item in enumerate(sorted(items, key=lambda i: i.rank), start=1):
        article = item.article
        content = f"Title: {article.title}\nSummary: {article.ai_summary or ''}"
        blocks.append(untrusted_block(f"candidate_article_{index}", content, 2500))
    return (
        "Do all of these articles cover the same specific story?\n\n"
        + "\n\n".join(blocks)
    )


def _parse_confirmation(raw: str) -> bool:
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:].lstrip()
    value = json.loads(text).get("same_story")
    if not isinstance(value, bool):
        raise ValueError("LLM cluster confirmation did not return a boolean same_story")
    return value


def _dissolve_cluster(items: list[BulletinItem]) -> None:
    for item in items:
        item.cluster_id = None
        item.is_cluster_lead = True
        item.cluster_size = 1


async def confirm_story_clusters(bulletin: Bulletin) -> None:
    """Confirm deterministic candidate clusters with one LLM call per cluster.

    Confirmation is fail-open: an unavailable or malformed LLM response leaves
    the deterministic candidate intact so bulletin generation remains reliable.
    """
    if not settings.LLM_CONFIRM_STORY_CLUSTERS:
        return

    candidates: dict[str, list[BulletinItem]] = {}
    for item in bulletin.items:
        if item.cluster_id:
            candidates.setdefault(item.cluster_id, []).append(item)

    for cluster_id, items in candidates.items():
        if len(items) < 2:
            continue
        try:
            raw = await llm_complete(
                _confirmation_prompt(items),
                max_tokens=40,
                system=CLUSTER_CONFIRMATION_SYSTEM_PROMPT,
            )
            if not _parse_confirmation(raw):
                _dissolve_cluster(items)
                logger.info(
                    "LLM rejected candidate cluster %s in bulletin %s",
                    cluster_id,
                    bulletin.bulletin_date,
                )
        except Exception as e:
            logger.warning(
                "LLM cluster confirmation failed for %s; keeping candidate: %s",
                cluster_id,
                e,
            )


def confirm_story_clusters_sync(bulletin: Bulletin) -> None:
    """Run async LLM confirmation from the synchronous bulletin builder."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(confirm_story_clusters(bulletin))
        return
    logger.warning("Skipping LLM cluster confirmation because an event loop is already running")
