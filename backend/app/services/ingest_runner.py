import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.models import Source, Article
from app.services.feed_fetcher import fetch_feed
from app.services.scraper import fetch_full_text
from app.services.dedup import url_hash, normalise_url
from app.services import job_state

logger = logging.getLogger(__name__)

SCRAPE_CONCURRENCY = 6
TITLE_DUP_JACCARD = 0.75
TITLE_DUP_WINDOW_DAYS = 14

_WORD_RE = re.compile(r"[a-z0-9]+")


def _title_tokens(title: str) -> frozenset[str]:
    return frozenset(w for w in _WORD_RE.findall(title.lower()) if len(w) > 3)


def _is_title_dup(tokens: frozenset[str], recent: list[frozenset[str]]) -> bool:
    """Near-duplicate title check — catches the same story syndicated across feeds."""
    if len(tokens) < 4:
        return False
    for other in recent:
        if not other:
            continue
        union = tokens | other
        if union and len(tokens & other) / len(union) >= TITLE_DUP_JACCARD:
            return True
    return False


async def run_ingest(db: Session) -> dict:
    sources = db.query(Source).filter(Source.is_active == True).all()
    run = job_state.start_run("ingest", total=len(sources))

    # Recent title token sets for cross-source near-dup detection
    title_cutoff = datetime.now(timezone.utc) - timedelta(days=TITLE_DUP_WINDOW_DAYS)
    recent_titles: list[frozenset[str]] = [
        _title_tokens(t)
        for (t,) in db.query(Article.title).filter(Article.created_at >= title_cutoff).all()
    ]

    sem = asyncio.Semaphore(SCRAPE_CONCURRENCY)

    async def _scrape(url: str):
        async with sem:
            return await fetch_full_text(url)

    for source in sources:
        result = job_state.SourceResult(name=source.name, url=source.url, status="ok")
        run.source_results.append(result)

        try:
            items = await fetch_feed(source.url)
        except Exception as e:
            source.consecutive_failures += 1
            source.last_error = str(e)
            db.commit()
            result.status = "error"
            result.error = str(e)
            run.failed += 1
            job_state.save_run(run)
            continue

        # Batch dedup: one IN query for the whole feed instead of one per entry
        candidates = []
        hashes = {}
        for item in items:
            raw_url = item["url"]
            if not raw_url:
                continue
            hashes[url_hash(raw_url)] = item
        if hashes:
            existing = {
                h for (h,) in db.query(Article.url_hash)
                .filter(Article.url_hash.in_(list(hashes.keys())))
                .all()
            }
        else:
            existing = set()

        for h, item in hashes.items():
            if h in existing:
                result.duplicates += 1
                run.processed += 1
                continue
            tokens = _title_tokens(item["title"])
            if _is_title_dup(tokens, recent_titles):
                logger.info("Skipping near-duplicate title: %s", item["title"][:80])
                result.duplicates += 1
                run.processed += 1
                continue
            candidates.append((h, item, tokens))

        # Scrape new articles concurrently
        scraped = await asyncio.gather(
            *(_scrape(item["url"]) for _, item, _ in candidates),
            return_exceptions=True,
        )

        for (h, item, tokens), scrape_result in zip(candidates, scraped):
            if isinstance(scrape_result, Exception):
                text, scraped_og = None, None
            else:
                text, scraped_og = scrape_result
            article = Article(
                source_id=source.id,
                url=normalise_url(item["url"]),
                url_hash=h,
                title=item["title"],
                published_at=item["published_at"],
                scraped_text=text,
                og_image=item.get("og_image") or scraped_og,
                enrichment_status="pending" if text else "no_text",
            )
            db.add(article)
            recent_titles.append(tokens)
            result.new_articles += 1
            run.succeeded += 1

        source.last_fetched_at = datetime.now(timezone.utc)
        source.consecutive_failures = 0
        source.last_error = None
        db.commit()
        job_state.save_run(run)

    job_state.finish_run(run, status="completed")
    logger.info("Ingest complete: %s", run.to_dict())
    return run.to_dict()
