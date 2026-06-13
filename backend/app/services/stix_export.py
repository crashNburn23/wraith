"""
STIX 2.1 and MISP export builders.

No external STIX library required — we construct the JSON directly since the
output is a narrow, well-defined subset: Bundle → Report + Indicator/ThreatActor/
Vulnerability objects derived from enriched articles.
"""
import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from app.models import Article


_STIX_SPEC_VER = "2.1"
_PRODUCER = "Wraith CTI Platform"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stix_id(obj_type: str, seed: str) -> str:
    uid = hashlib.sha256(seed.encode()).hexdigest()[:32]
    return f"{obj_type}--{uid[:8]}-{uid[8:12]}-{uid[12:16]}-{uid[16:20]}-{uid[20:]}"


def _ioc_pattern(ioc_type: str, value: str) -> str | None:
    v = value.replace("'", "\\'")
    if ioc_type == "ip":
        return f"[network-traffic:dst_ref.type = 'ipv4-addr' AND network-traffic:dst_ref.value = '{v}']"
    if ioc_type == "domain":
        return f"[domain-name:value = '{v}']"
    if ioc_type == "url":
        return f"[url:value = '{v}']"
    if ioc_type == "hash":
        if len(value) == 32:
            return f"[file:hashes.MD5 = '{v}']"
        if len(value) == 40:
            return f"[file:hashes.'SHA-1' = '{v}']"
        if len(value) == 64:
            return f"[file:hashes.'SHA-256' = '{v}']"
    if ioc_type == "email":
        return f"[email-addr:value = '{v}']"
    return None


def _cve_pattern(cve_id: str) -> str:
    return f"[vulnerability:name = '{cve_id}']"


def article_to_stix_objects(article: Article) -> list[dict[str, Any]]:
    """Convert a single enriched article to a list of STIX 2.1 objects."""
    objects: list[dict] = []
    now = _now()
    pub = (
        article.published_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        if article.published_at else now
    )

    report_refs: list[str] = []

    # Indicators (IOCs)
    for ioc in article.iocs:
        pattern = _ioc_pattern(ioc.ioc_type, ioc.value)
        if not pattern:
            continue
        ioc_id = _stix_id("indicator", f"ioc:{ioc.value}")
        obj: dict = {
            "type": "indicator",
            "spec_version": _STIX_SPEC_VER,
            "id": ioc_id,
            "created": now,
            "modified": now,
            "name": ioc.value,
            "indicator_types": ["malicious-activity"],
            "pattern": pattern,
            "pattern_type": "stix",
            "valid_from": pub,
        }
        objects.append(obj)
        report_refs.append(ioc_id)

    # Threat actors
    for aa in article.article_actors:
        if not aa.actor:
            continue
        actor_id = _stix_id("threat-actor", f"actor:{aa.actor.name}")
        obj = {
            "type": "threat-actor",
            "spec_version": _STIX_SPEC_VER,
            "id": actor_id,
            "created": now,
            "modified": now,
            "name": aa.actor.name,
            "threat_actor_types": ["nation-state"],
        }
        if aa.actor.aliases:
            obj["aliases"] = aa.actor.aliases
        objects.append(obj)
        report_refs.append(actor_id)

    # Vulnerabilities (CVEs)
    for mention in article.cve_mentions:
        vuln_id = _stix_id("vulnerability", f"cve:{mention.cve_id}")
        obj = {
            "type": "vulnerability",
            "spec_version": _STIX_SPEC_VER,
            "id": vuln_id,
            "created": now,
            "modified": now,
            "name": mention.cve_id,
            "external_references": [
                {
                    "source_name": "cve",
                    "external_id": mention.cve_id,
                    "url": f"https://nvd.nist.gov/vuln/detail/{mention.cve_id}",
                }
            ],
        }
        objects.append(obj)
        report_refs.append(vuln_id)

    # Report
    report_id = _stix_id("report", f"article:{article.id}")
    report: dict = {
        "type": "report",
        "spec_version": _STIX_SPEC_VER,
        "id": report_id,
        "created": now,
        "modified": now,
        "name": article.title,
        "description": article.ai_summary or "",
        "published": pub,
        "report_types": ["threat-report"],
        "object_refs": report_refs,
        "external_references": [{"source_name": "url", "url": article.url}],
        "labels": list(filter(None, [
            article.threat_category,
            *(article.sector_targets or []),
        ])),
    }
    objects.insert(0, report)

    return objects


def build_stix_bundle(articles: list[Article]) -> dict[str, Any]:
    """Build a STIX 2.1 Bundle from a list of enriched articles."""
    all_objects: list[dict] = []
    seen_ids: set[str] = set()

    for article in articles:
        for obj in article_to_stix_objects(article):
            if obj["id"] not in seen_ids:
                all_objects.append(obj)
                seen_ids.add(obj["id"])

    bundle_id = _stix_id("bundle", f"bundle:{_now()}")
    return {
        "type": "bundle",
        "id": bundle_id,
        "objects": all_objects,
    }


# ─── MISP event format ────────────────────────────────────────────────────────

_MISP_CATEGORY = {
    "ip": ("Network activity", "ip-dst"),
    "domain": ("Network activity", "domain"),
    "url": ("Network activity", "url"),
    "email": ("Payload delivery", "email-src"),
    "hash": ("Payload delivery", "md5"),  # refined per length below
}

_HASH_TYPE = {32: "md5", 40: "sha1", 64: "sha256"}


def build_misp_event(article: Article) -> dict[str, Any]:
    """Build a simplified MISP event dict for a single article."""
    attributes = []

    for ioc in article.iocs:
        cat, atype = _MISP_CATEGORY.get(ioc.ioc_type, ("External analysis", "text"))
        if ioc.ioc_type == "hash":
            atype = _HASH_TYPE.get(len(ioc.value), "sha256")
        attributes.append({
            "category": cat,
            "type": atype,
            "value": ioc.value,
            "to_ids": True,
            "comment": ioc.source_excerpt or "",
        })

    for mention in article.cve_mentions:
        attributes.append({
            "category": "External analysis",
            "type": "vulnerability",
            "value": mention.cve_id,
            "to_ids": False,
        })

    for aa in article.article_actors:
        if aa.actor:
            attributes.append({
                "category": "Attribution",
                "type": "threat-actor",
                "value": aa.actor.name,
                "to_ids": False,
            })

    tags = []
    if article.threat_category:
        tags.append({"name": f"wraith:category={article.threat_category}"})
    for sector in (article.sector_targets or []):
        tags.append({"name": f"wraith:sector={sector}"})

    pub = (
        int(article.published_at.timestamp())
        if article.published_at else
        int(datetime.now(timezone.utc).timestamp())
    )

    return {
        "Event": {
            "info": article.title,
            "date": article.published_at.strftime("%Y-%m-%d") if article.published_at else None,
            "threat_level_id": max(1, min(4, 5 - round((article.ai_severity_score or 0) / 25))),
            "analysis": 2,  # completed
            "distribution": 0,  # your org only
            "published": False,
            "timestamp": str(pub),
            "Attribute": attributes,
            "Tag": tags,
            "Org": {"name": _PRODUCER},
            "ExternalLink": article.url,
        }
    }
