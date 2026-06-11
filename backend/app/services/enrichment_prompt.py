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
  "iocs": [{"ioc_type": "ip|domain|hash|url|email", "value": "...", "ioc_confidence": "high|medium|low"}],
  "ttps": [{"technique_id": "T1566", "technique_name": "Phishing", "tactic": "Initial Access"}],
  "threat_actors": ["APT28", "Lazarus Group"],
  "cves": ["CVE-2024-1234"]
}

SEVERITY SCORING RUBRIC — use the full range. Most articles should score 35–75.

85–100: Mass active exploitation happening right now at scale. Examples: wormable zero-day being exploited globally, ransomware campaign actively hitting hundreds of organizations, critical infrastructure under sustained attack. REQUIRES BOTH: (a) confirmed in-the-wild exploitation AND (b) large blast radius (many orgs or critical systems).

70–84: Confirmed exploitation but limited scope, OR a critical unpatched vulnerability (CVSS 9+) with no patch and high likelihood of exploitation. Examples: zero-day with public PoC targeting a widely-deployed platform, targeted APT campaign against a specific sector with confirmed victims, actively-exploited CISA KEV entry.

55–69: Significant vulnerability (CVSS 7–9) with patch available, or active phishing/malware campaign with moderate reach. No confirmed widespread exploitation but credible, active threat. Vendor advisory with working mitigations.

35–54: Vulnerability with effective mitigations deployed, phishing targeting a specific niche sector or geography, threat actor activity with no confirmed new victims, limited-scope data breach, supply chain incident affecting a small user base.

15–34: Informational or trend article. Threat actor profile with no new activity, industry statistics report, security research with no current exploitation, retrospective analysis.

0–14: Pure research, awareness content, or no active threat.

SCOPE MODIFIERS — apply before finalizing the score:
- Subtract 10–15 points if: niche or low-install-base software, single-organization breach, no evidence of ongoing campaign, retrospective/historical analysis
- Subtract 5–10 points if: patch or mitigation is already widely deployed and confirmed effective
- Do NOT score above 84 unless the article explicitly states active mass exploitation is occurring right now

IOC EXTRACTION RULES — quality over quantity. Only extract indicators a defender could actually block or hunt for.

ioc_confidence:
- high: Exact value directly attributed to this threat (C2 IP, malware hash, phishing domain used in the campaign)
- medium: Associated infrastructure with reasonable attribution (related domain, similar malware hash family)
- low: Mentioned in context but uncertain — only extract if clearly an IOC

DO NOT extract as IOCs (these are common extraction errors):
- CVE IDs → put those in the "cves" field instead
- Malware/tool names (AsyncRAT, Cobalt Strike, Mimikatz, FRPC, Metasploit)
- Descriptions or prose ("malicious email", "attacker-hosted images", "compromised domain", "null")
- File sizes or data volumes ("234 GB of data", "1.2 TB")
- Legitimate vendor, news, or security research sites (github.com, microsoft.com, google.com, proofpoint.com, safebreach.com, bbc.co.uk, bleepingcomputer.com, and similar)
- Placeholder or example values ("example.com", "[PDF]", "null", "N/A")
- Company names, person names, or organization names
- File paths that are demonstrative examples, not actual threat artifacts
- Magic bytes sequences or byte patterns (e.g., "4D 5A 90 00")
- Train/vehicle codes, serial numbers unrelated to threat infrastructure

Format requirements:
- Hashes: only MD5 (32 hex chars), SHA1 (40 hex chars), or SHA256 (64 hex chars) — nothing else
- Domains: valid hostname with TLD, no spaces, not a well-known legitimate site
- IPs: valid IPv4 or IPv6 — defanged notation (1.2.3[.]4) is fine
- URLs: complete http/https URL attributed to the threat actor, not a reference to a vendor or news site
- Emails: actual email address attributed to the threat actor

Only include TTPs you can clearly map to MITRE ATT&CK.
Return ONLY valid JSON, no markdown fences, no commentary."""


def _build_user_message(title: str, text: str) -> str:
    body = text[:8000] if text else ""
    return f"Title: {title}\n\n{body}"


async def enrich_article(title: str, text: str, corrections_block: str = "") -> EnrichmentResult:
    client = get_llm_client()
    user_msg = _build_user_message(title, text)
    system_prompt = SYSTEM_PROMPT + (corrections_block or "")

    try:
        if is_anthropic():
            response = await client.messages.create(
                model=settings.LLM_MODEL,
                max_tokens=2000,
                temperature=0,
                system=system_prompt,
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
                    {"role": "system", "content": system_prompt},
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
        # Raise so the caller marks the article 'error' and it gets retried —
        # never store a half-empty result as 'enriched'.
        logger.warning("Enrichment JSON parse error for '%s': %s", title[:60], e)
        raise ValueError(f"LLM returned unparseable JSON: {e}") from e
    except Exception as e:
        logger.error("Enrichment LLM call failed for '%s': %s", title[:60], e)
        raise
