import logging
import re
from datetime import datetime, timezone
from typing import Iterator
import feedparser
import httpx

# Matches & not already part of a valid XML/HTML entity reference
_BARE_AMP = re.compile(rb"&(?!(?:[a-zA-Z][a-zA-Z0-9]*|#[0-9]+|#x[0-9a-fA-F]+);)")
# Characters invalid in XML 1.0 (excluding tab \x09, LF \x0a, CR \x0d)
_INVALID_XML = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]")

logger = logging.getLogger(__name__)


def _to_utc(struct_time) -> datetime | None:
    if not struct_time:
        return None
    try:
        import calendar
        ts = calendar.timegm(struct_time)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return None


async def fetch_feed(url: str, timeout: int = 20) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content = resp.content
    except Exception as e:
        logger.warning("Feed fetch failed %s: %s", url, e)
        raise

    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        sanitized = _INVALID_XML.sub(b"", _BARE_AMP.sub(b"&amp;", content))
        parsed = feedparser.parse(sanitized)
        if parsed.bozo and not parsed.entries:
            logger.warning("Feed parse error for %s: %s", url, parsed.bozo_exception)
            raise ValueError(f"Feed parse error: {parsed.bozo_exception}")
        logger.info("Feed recovered after XML sanitization: %s", url)

    items = []
    for entry in parsed.entries:
        items.append({
            "url": entry.get("link") or entry.get("id", ""),
            "title": entry.get("title", "Untitled"),
            "published_at": _to_utc(entry.get("published_parsed") or entry.get("updated_parsed")),
            "og_image": _extract_image(entry),
        })
    return items


def _extract_image(entry) -> str | None:
    for thumb in (entry.get("media_thumbnail") or []):
        if thumb.get("url"):
            return thumb["url"]
    for mc in (entry.get("media_content") or []):
        if mc.get("url") and "image" in mc.get("type", ""):
            return mc["url"]
    for link in (entry.get("links") or []):
        if link.get("rel") == "enclosure" and "image" in link.get("type", "") and link.get("href"):
            return link["href"]
    return None
