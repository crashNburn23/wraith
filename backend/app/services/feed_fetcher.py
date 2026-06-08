import logging
from datetime import datetime, timezone
from typing import Iterator
import feedparser
import httpx

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
        logger.warning("Feed parse error for %s: %s", url, parsed.bozo_exception)
        return []

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
