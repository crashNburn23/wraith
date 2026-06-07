import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import Source, Article
from app.services.feed_fetcher import fetch_feed
from app.services.scraper import fetch_full_text
from app.services.dedup import url_hash, normalise_url
from app.services import job_state

logger = logging.getLogger(__name__)


async def run_ingest(db: Session) -> dict:
    sources = db.query(Source).filter(Source.is_active == True).all()
    run = job_state.start_run("ingest", total=len(sources))

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
            continue

        for item in items:
            raw_url = item["url"]
            if not raw_url:
                continue

            h = url_hash(raw_url)
            if db.query(Article).filter(Article.url_hash == h).first():
                result.duplicates += 1
                run.processed += 1
                continue

            text = await fetch_full_text(raw_url)
            article = Article(
                source_id=source.id,
                url=normalise_url(raw_url),
                url_hash=h,
                title=item["title"],
                published_at=item["published_at"],
                scraped_text=text,
                enrichment_status="pending" if text else "no_text",
            )
            db.add(article)
            result.new_articles += 1
            run.succeeded += 1

        source.last_fetched_at = datetime.now(timezone.utc)
        source.consecutive_failures = 0
        source.last_error = None
        db.commit()

    job_state.finish_run(run, status="completed")
    logger.info("Ingest complete: %s", run.to_dict())
    return run.to_dict()
