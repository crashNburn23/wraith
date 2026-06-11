import logging
from datetime import datetime, timezone, timedelta

import httpx
from sqlalchemy.orm import Session
from app.models import CVEMention, CVERecord
from app.core.config import settings
from app.services.llm_client import llm_complete

logger = logging.getLogger(__name__)

NVD_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"
EPSS_BASE = "https://api.first.org/data/v1/epss"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

RESYNC_AFTER_DAYS = 7        # don't hammer NVD for records synced recently
MAX_AI_SUMMARIES_PER_RUN = 20


async def _fetch_nvd(cve_id: str) -> dict | None:
    params = {"cveId": cve_id}
    headers = {}
    if settings.NVD_API_KEY:
        headers["apiKey"] = settings.NVD_API_KEY
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(NVD_BASE, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
            vulns = data.get("vulnerabilities", [])
            if not vulns:
                return None
            cve = vulns[0]["cve"]
            metrics = cve.get("metrics", {})
            cvss = None
            for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
                entries = metrics.get(key, [])
                if entries:
                    cvss = entries[0]["cvssData"]["baseScore"]
                    break
            desc = ""
            for d in cve.get("descriptions", []):
                if d["lang"] == "en":
                    desc = d["value"]
                    break
            return {"cvss_score": cvss, "nvd_description": desc}
    except Exception as e:
        logger.warning("NVD fetch failed for %s: %s", cve_id, e)
        return None


async def _fetch_epss(cve_id: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(EPSS_BASE, params={"cve": cve_id})
            r.raise_for_status()
            data = r.json().get("data", [])
            if not data:
                return None
            return {
                "epss_score": float(data[0]["epss"]),
                "epss_percentile": float(data[0]["percentile"]),
            }
    except Exception as e:
        logger.warning("EPSS fetch failed for %s: %s", cve_id, e)
        return None


async def _fetch_kev() -> set[str]:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(KEV_URL)
            r.raise_for_status()
            vulns = r.json().get("vulnerabilities", [])
            return {v["cveID"] for v in vulns}
    except Exception as e:
        logger.warning("KEV fetch failed: %s", e)
        return set()


async def _plain_english_summary(cve_id: str, description: str) -> str | None:
    """One-line analyst-friendly rewrite of the NVD description."""
    try:
        text = await llm_complete(
            f"Rewrite this CVE description as ONE plain-English sentence for a security "
            f"analyst: what is affected and what an attacker can do. No jargon beyond "
            f"product names, no CVE id, no preamble.\n\n{cve_id}: {description[:1500]}",
            max_tokens=120,
        )
        return text.strip().strip('"') or None
    except Exception as e:
        logger.warning("CVE summary generation failed for %s: %s", cve_id, e)
        return None


def _is_fresh(record: CVERecord) -> bool:
    if record.cvss_score is None:
        return False
    updated = record.updated_at
    if updated is None:
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - updated < timedelta(days=RESYNC_AFTER_DAYS)


async def sync_cves_for_articles(db: Session) -> dict:
    mentions = db.query(CVEMention).all()
    cve_ids = {m.cve_id for m in mentions if m.cve_id}
    if not cve_ids:
        return {"synced": 0, "skipped_fresh": 0}

    kev_set = await _fetch_kev()
    synced = 0
    skipped = 0
    summaries_generated = 0

    for cve_id in cve_ids:
        record = db.query(CVERecord).filter(CVERecord.cve_id == cve_id).first()
        if not record:
            record = CVERecord(cve_id=cve_id)
            db.add(record)

        # KEV membership is free (already downloaded) — always update it
        if kev_set:
            record.in_kev = cve_id in kev_set

        if _is_fresh(record):
            skipped += 1
            continue

        nvd = await _fetch_nvd(cve_id)
        epss = await _fetch_epss(cve_id)

        if nvd:
            record.cvss_score = nvd.get("cvss_score")
            record.nvd_description = nvd.get("nvd_description")
        if epss:
            record.epss_score = epss.get("epss_score")
            record.epss_percentile = epss.get("epss_percentile")

        if (
            not record.ai_summary
            and record.nvd_description
            and summaries_generated < MAX_AI_SUMMARIES_PER_RUN
        ):
            record.ai_summary = await _plain_english_summary(cve_id, record.nvd_description)
            if record.ai_summary:
                summaries_generated += 1

        synced += 1
        db.commit()  # commit per record so a crash keeps progress

    db.commit()
    return {"synced": synced, "skipped_fresh": skipped, "summaries_generated": summaries_generated}
