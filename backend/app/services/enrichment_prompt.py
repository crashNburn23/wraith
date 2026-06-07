import json
import logging
from app.services.llm_client import get_llm_client, is_anthropic
from app.services.enrichment_schema import EnrichmentResult
from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a cybersecurity threat intelligence analyst.
Analyze the article and extract structured intelligence as JSON with these exact keys:

{
  "summary": "2-3 sentence plain-English summary focused on threat impact",
  "threat_category": "one of: Malware, Ransomware, APT, Phishing, Vulnerability, Data Breach, DDoS, Supply Chain, Insider Threat, General",
  "severity_score": <integer 0-100>,
  "sector_targets": ["Finance", "Healthcare", ...],
  "geo_origin": "country or region the threat originates from, or null",
  "geo_targets": ["US", "EU", ...],
  "iocs": [{"ioc_type": "ip|domain|hash|url|email", "value": "..."}],
  "ttps": [{"technique_id": "T1566", "technique_name": "Phishing", "tactic": "Initial Access"}],
  "threat_actors": ["APT28", "Lazarus Group"],
  "cves": ["CVE-2024-1234"]
}

Rules:
- severity_score: 0=informational, 50=moderate threat, 80+=critical/active exploitation
- Only include IOCs that appear explicitly in the text
- Only include TTPs you can clearly map to MITRE ATT&CK
- Return ONLY valid JSON, no markdown fences, no commentary"""


def _build_user_message(title: str, text: str) -> str:
    body = text[:8000] if text else ""
    return f"Title: {title}\n\n{body}"


async def enrich_article(title: str, text: str) -> EnrichmentResult:
    client = get_llm_client()
    user_msg = _build_user_message(title, text)

    try:
        if is_anthropic():
            response = await client.messages.create(
                model=settings.LLM_MODEL,
                max_tokens=2000,
                temperature=0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = response.content[0].text.strip()
        else:
            response = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                temperature=0,
                max_tokens=2000,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
            )
            raw = response.choices[0].message.content.strip()

        # Strip markdown fences if model ignores the instruction
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:].lstrip()

        data = json.loads(raw)
        return EnrichmentResult(**data)

    except json.JSONDecodeError as e:
        logger.warning("Enrichment JSON parse error for '%s': %s", title[:60], e)
        return EnrichmentResult(summary="Failed to parse LLM response.")
    except Exception as e:
        logger.error("Enrichment LLM call failed for '%s': %s", title[:60], e)
        raise
