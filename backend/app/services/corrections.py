"""
Enrichment correction memory.

Every analyst correction (deleting a bogus IOC, whitelisting a domain, fixing
a technique id) is recorded and the most recent ones are injected into the
enrichment prompt as concrete 'do not repeat this mistake' examples — the
mechanism by which enrichment quality improves over time.
"""
from sqlalchemy.orm import Session
from app.models import EnrichmentCorrection

MAX_PROMPT_CORRECTIONS = 12


def record_correction(
    db: Session,
    entity_type: str,
    action: str,
    original_value: str,
    corrected_value: str | None = None,
) -> None:
    if not original_value:
        return
    db.add(EnrichmentCorrection(
        entity_type=entity_type,
        action=action,
        original_value=original_value[:500],
        corrected_value=(corrected_value or None) and corrected_value[:500],
    ))
    # caller commits


def corrections_prompt_block(db: Session) -> str:
    """Returns a prompt section listing recent analyst corrections, or ''."""
    rows = (
        db.query(EnrichmentCorrection)
        .order_by(EnrichmentCorrection.created_at.desc())
        .limit(MAX_PROMPT_CORRECTIONS)
        .all()
    )
    if not rows:
        return ""
    lines = []
    for r in rows:
        if r.action in ("deleted", "whitelisted"):
            lines.append(f'- Do NOT extract "{r.original_value}" as a {r.entity_type} — the analyst removed it as a false positive.')
        elif r.action == "edited" and r.corrected_value:
            lines.append(f'- The analyst corrected the {r.entity_type} "{r.original_value}" to "{r.corrected_value}" — prefer the corrected form.')
    if not lines:
        return ""
    return (
        "\n\nPAST ANALYST CORRECTIONS — this analyst reviewed previous extractions "
        "and fixed these mistakes. Do not repeat them:\n" + "\n".join(lines)
    )
