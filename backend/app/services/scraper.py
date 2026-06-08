import logging
import re
import httpx
import trafilatura

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (CTI-Platform/1.0; +https://localhost) research bot",
    "Accept-Language": "en-US,en;q=0.9",
}

_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_OG_IMAGE_RE2 = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    re.IGNORECASE,
)


def _extract_og_image(html: str) -> str | None:
    m = _OG_IMAGE_RE.search(html) or _OG_IMAGE_RE2.search(html)
    return m.group(1).strip() if m else None


async def fetch_full_text(url: str, timeout: int = 15) -> tuple[str | None, str | None]:
    """Returns (text, og_image). Either may be None."""
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.warning("HTTP fetch failed for %s: %s", url, e)
        return None, None

    og_image = _extract_og_image(html)

    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        no_fallback=False,
    )
    if not text or len(text) < 100:
        logger.debug("Trafilatura extracted too little from %s", url)
        return None, og_image
    return text, og_image
