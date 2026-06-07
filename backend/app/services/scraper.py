import logging
import httpx
import trafilatura

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (CTI-Platform/1.0; +https://localhost) research bot",
    "Accept-Language": "en-US,en;q=0.9",
}


async def fetch_full_text(url: str, timeout: int = 15) -> str | None:
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.warning("HTTP fetch failed for %s: %s", url, e)
        return None

    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
    )
    if not text or len(text) < 100:
        logger.debug("Trafilatura extracted too little from %s", url)
        return None
    return text
