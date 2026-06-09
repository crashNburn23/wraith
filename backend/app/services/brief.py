import logging
from datetime import datetime, timezone, date, timedelta
from sqlalchemy.orm import Session
from app.models import Bulletin, BulletinItem, Article
from app.services.llm_client import get_llm_client, is_anthropic
from app.core.config import settings

logger = logging.getLogger(__name__)

BRIEF_SYSTEM_PROMPT = """You are a senior CTI analyst writing a daily intelligence brief for a security team.

Write a 3-paragraph daily brief covering the top threats provided below.

Paragraph 1 — Executive lead: 3–4 sentences in plain English suitable for a CISO. Name the dominant threat theme of the day, its potential business impact, and who is most at risk. Avoid acronyms unless you define them. No bullet points.

Paragraph 2 — Technical depth on the primary threat: Expand on the highest-severity item. Name the specific actor (and nation-state attribution if known), CVE identifiers, MITRE ATT&CK techniques, targeted geographies and sectors. Be precise and specific.

Paragraph 3 — Secondary threats and defender guidance: Briefly cover the other notable threats and identify any common thread across today's intelligence. Close with 1–2 sentences of concrete, prioritised defender guidance.

Rules:
- Flowing prose only — no bullet points, no headers, no markdown formatting
- Nation-state attribution should be stated plainly when present
- Keep total length between 220–290 words
- Return only the three paragraphs separated by a blank line, no preamble or sign-off"""


def _build_article_block(rank: int, article: Article) -> str:
    actors = [aa.actor.name for aa in article.article_actors if aa.actor]
    ttps = [t.technique_name for t in article.ttp_tags]
    cves = [m.cve_id for m in article.cve_mentions]
    sectors = article.sector_targets or []
    geo_targets = article.geo_targets or []
    geo_origin = article.geo_origin or ""

    lines = [
        f"[ARTICLE {rank}] Severity: {int(article.ai_severity_score or 0)}/100  Category: {article.threat_category or 'General'}",
        f"Title: {article.title}",
        f"Summary: {article.ai_summary or ''}",
    ]
    if actors:
        lines.append(f"Threat actors: {', '.join(actors)}")
    if cves:
        lines.append(f"CVEs: {', '.join(cves)}")
    if ttps:
        lines.append(f"Techniques: {', '.join(ttps[:5])}")
    if geo_origin:
        lines.append(f"Origin: {geo_origin}")
    if geo_targets:
        lines.append(f"Targets: {', '.join(geo_targets)}")
    if sectors:
        lines.append(f"Sectors: {', '.join(sectors)}")
    if article.scraped_text:
        lines.append(f"Article text (excerpt): {article.scraped_text[:2000]}")

    return "\n".join(lines)


async def generate_brief(db: Session, for_date: date | None = None) -> str | None:
    if for_date is None:
        for_date = date.today()
    date_str = for_date.isoformat()

    bulletin = db.query(Bulletin).filter(Bulletin.bulletin_date == date_str).first()
    if not bulletin or not bulletin.items:
        logger.warning("No bulletin found for %s — skipping brief generation", date_str)
        return None

    # Only consider articles published in the last 24 hours
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_articles = []
    for item in bulletin.items:
        article = db.query(Article).filter(Article.id == item.article_id).first()
        if not article:
            continue
        pub = article.published_at
        if pub:
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            if pub < cutoff:
                continue
        recent_articles.append(article)
        if len(recent_articles) == 3:
            break

    # Fall back to top 3 overall if nothing is recent enough
    if not recent_articles:
        logger.info("No articles within 24h for brief on %s — falling back to top 3", date_str)
        recent_articles = [
            db.query(Article).filter(Article.id == item.article_id).first()
            for item in bulletin.items[:3]
        ]
        recent_articles = [a for a in recent_articles if a]

    articles = recent_articles

    if not articles:
        return None

    article_blocks = "\n\n".join(
        _build_article_block(rank, article)
        for rank, article in enumerate(articles, start=1)
    )

    user_msg = f"Today's date: {date_str}\n\nTop {len(articles)} articles for today's bulletin:\n\n{article_blocks}"

    try:
        client = get_llm_client()
        if is_anthropic():
            response = await client.messages.create(
                model=settings.LLM_MODEL,
                max_tokens=600,
                temperature=0.3,
                system=BRIEF_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            brief_text = response.content[0].text.strip()
        else:
            response = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                temperature=0.3,
                max_tokens=600,
                messages=[
                    {"role": "system", "content": BRIEF_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
            )
            brief_text = response.choices[0].message.content.strip()

        # Append source citations in a parseable format
        sources = "||".join(f"{a.id}::{a.title}" for a in articles)
        brief_with_sources = brief_text + f"\n\nSOURCES:{sources}"

        bulletin.brief = brief_with_sources
        bulletin.brief_generated_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Daily brief generated for %s (%d words)", date_str, len(brief_text.split()))
        return brief_with_sources

    except Exception as e:
        logger.error("Brief generation failed for %s: %s", date_str, e)
        return None
