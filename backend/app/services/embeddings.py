"""
Optional semantic embeddings via Ollama's OpenAI-compatible /v1/embeddings.

Disabled unless EMBEDDING_MODEL is set (e.g. nomic-embed-text). Embeddings are
served by Ollama at LLM_BASE_URL even when LLM_PROVIDER=anthropic, since
Anthropic has no embeddings API. All failures degrade gracefully to None so
the keyword fallbacks keep working.
"""
import logging
import math
from functools import lru_cache

from app.core.config import settings

logger = logging.getLogger(__name__)

_warned = False


def enabled() -> bool:
    return bool(settings.EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def _client():
    from openai import AsyncOpenAI
    return AsyncOpenAI(base_url=settings.LLM_BASE_URL, api_key="ollama")


async def embed_text(text: str) -> list[float] | None:
    global _warned
    if not enabled() or not text.strip():
        return None
    try:
        resp = await _client().embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=text[:4000],
        )
        return list(resp.data[0].embedding)
    except Exception as e:
        if not _warned:
            logger.warning("Embedding call failed (model=%s): %s — embeddings disabled for this run",
                           settings.EMBEDDING_MODEL, e)
            _warned = True
        return None


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
