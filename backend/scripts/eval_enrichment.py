"""
Enrichment evaluation harness.

Keeps prompt/model changes honest: run a gold set of manually verified
articles through the current enrichment pipeline and diff the extractions.

Usage:
  # 1. Export current enriched articles as a starting gold set (review by hand!)
  .venv/bin/python3 -m scripts.eval_enrichment export > gold_set.json

  # 2. After changing the prompt or model, score against the gold set
  .venv/bin/python3 -m scripts.eval_enrichment run gold_set.json

Gold set format:
[{
  "title": "...",
  "text": "...",
  "expected": {
    "threat_category": "Ransomware",
    "severity_score": 75,
    "cves": ["CVE-2024-1234"],
    "threat_actors": ["APT28"],
    "iocs_by_type": {
      "ip": ["1.2.3.4"],
      "domain": ["evil.com"],
      "hash": [],
      "url": [],
      "email": []
    },
    "ttps": ["T1566", "T1486"],
    "geo_origin": "Russia",
    "geo_targets": ["US", "EU"],
    "sector_targets": ["Finance", "Healthcare"]
  }
}, ...]
"""
import asyncio
import json
import sys

from app.db.session import SessionLocal
from app.models import Article
from app.services.enrichment_prompt import enrich_article


def _f1(expected: set, got: set) -> float:
    if not expected and not got:
        return 1.0
    if not expected or not got:
        return 0.0
    tp = len(expected & got)
    p = tp / len(got)
    r = tp / len(expected)
    return 2 * p * r / (p + r) if (p + r) else 0.0


def export_gold_set(limit: int = 20) -> None:
    db = SessionLocal()
    try:
        articles = (
            db.query(Article)
            .filter(Article.enrichment_status == "enriched", Article.scraped_text.isnot(None))
            .order_by(Article.enriched_at.desc())
            .limit(limit)
            .all()
        )
        out = []
        for a in articles:
            iocs_by_type: dict[str, list[str]] = {t: [] for t in ("ip", "domain", "hash", "url", "email")}
            for i in a.iocs:
                iocs_by_type.setdefault(i.ioc_type, []).append(i.value)
            out.append({
                "title": a.title,
                "text": a.scraped_text[:8000],
                "expected": {
                    "threat_category": a.threat_category,
                    "severity_score": a.ai_severity_score,
                    "cves": [m.cve_id for m in a.cve_mentions],
                    "threat_actors": [aa.actor.name for aa in a.article_actors if aa.actor],
                    "iocs_by_type": iocs_by_type,
                    "ttps": [t.technique_id for t in a.ttp_tags],
                    "geo_origin": a.geo_origin,
                    "geo_targets": a.geo_targets or [],
                    "sector_targets": a.sector_targets or [],
                },
            })
        json.dump(out, sys.stdout, indent=2)
        print(f"\n# exported {len(out)} articles — REVIEW AND CORRECT before using as gold", file=sys.stderr)
    finally:
        db.close()


async def run_eval(path: str) -> None:
    gold = json.load(open(path))
    n = len(gold)

    cat_hits = 0
    sev_diffs = 0.0
    cve_f1_sum = 0.0
    actor_f1_sum = 0.0
    ioc_f1_by_type: dict[str, list[float]] = {}
    ttp_f1_sum = 0.0
    geo_origin_hits = 0
    geo_target_f1_sum = 0.0
    sector_f1_sum = 0.0
    errors = 0

    for i, case in enumerate(gold):
        exp = case["expected"]
        try:
            result = await enrich_article(case["title"], case["text"])
        except Exception as e:
            print(f"[{i+1}/{n}] ERROR: {case['title'][:60]} — {e}")
            errors += 1
            continue

        # Category
        cat_ok = result.threat_category == exp.get("threat_category")
        cat_hits += cat_ok

        # Severity
        sev_diff = abs((result.severity_score or 0) - (exp.get("severity_score") or 0))
        sev_diffs += sev_diff

        # CVEs
        cve_f1 = _f1(
            set(exp.get("cves", [])),
            set(result.cves),
        )
        cve_f1_sum += cve_f1

        # Actors
        actor_f1 = _f1(
            {a.lower() for a in exp.get("threat_actors", [])},
            {a.lower() for a in result.threat_actors},
        )
        actor_f1_sum += actor_f1

        # IOCs by type
        exp_iocs = exp.get("iocs_by_type", {})
        got_iocs: dict[str, set[str]] = {}
        for ioc in result.iocs:
            got_iocs.setdefault(ioc.ioc_type, set()).add(ioc.value.lower())

        ioc_type_f1s: list[float] = []
        for ioc_type in ("ip", "domain", "hash", "url", "email"):
            exp_set = {v.lower() for v in exp_iocs.get(ioc_type, [])}
            got_set = got_iocs.get(ioc_type, set())
            f = _f1(exp_set, got_set)
            ioc_f1_by_type.setdefault(ioc_type, []).append(f)
            ioc_type_f1s.append(f)

        # TTPs
        ttp_f1 = _f1(
            set(exp.get("ttps", [])),
            {t.technique_id for t in result.ttps},
        )
        ttp_f1_sum += ttp_f1

        # Geo origin (exact match, case-insensitive)
        exp_geo = (exp.get("geo_origin") or "").lower()
        got_geo = (result.geo_origin or "").lower()
        geo_ok = exp_geo == got_geo
        geo_origin_hits += geo_ok

        # Geo targets
        geo_target_f1 = _f1(
            {g.lower() for g in exp.get("geo_targets", [])},
            {g.lower() for g in result.geo_targets},
        )
        geo_target_f1_sum += geo_target_f1

        # Sectors
        sector_f1 = _f1(
            {s.lower() for s in exp.get("sector_targets", [])},
            {s.lower() for s in result.sector_targets},
        )
        sector_f1_sum += sector_f1

        ioc_summary = " ".join(f"{t}={ioc_f1_by_type[t][-1]:.2f}" for t in ("ip", "domain", "hash", "url", "email"))
        print(
            f"[{i+1}/{n}] cat={'✓' if cat_ok else '✗'} sevΔ={sev_diff:.0f} "
            f"cveF1={cve_f1:.2f} actorF1={actor_f1:.2f} ttpF1={ttp_f1:.2f} "
            f"geo={'✓' if geo_ok else '✗'} geoTgtF1={geo_target_f1:.2f} sectorF1={sector_f1:.2f}  "
            f"ioc[{ioc_summary}]  {case['title'][:50]}"
        )

    scored = n - errors
    if scored == 0:
        print("\nNo articles scored successfully.")
        return

    print("\n=== SUMMARY ===")
    print(f"articles scored    : {scored}/{n}")
    print(f"category accuracy  : {cat_hits}/{scored} ({cat_hits/scored:.0%})")
    print(f"mean severity Δ    : {sev_diffs/scored:.1f}")
    print(f"mean CVE F1        : {cve_f1_sum/scored:.2f}")
    print(f"mean actor F1      : {actor_f1_sum/scored:.2f}")
    print(f"mean TTP F1        : {ttp_f1_sum/scored:.2f}")
    print(f"geo origin accuracy: {geo_origin_hits}/{scored} ({geo_origin_hits/scored:.0%})")
    print(f"geo target F1      : {geo_target_f1_sum/scored:.2f}")
    print(f"sector F1          : {sector_f1_sum/scored:.2f}")
    print("IOC F1 by type:")
    for ioc_type in ("ip", "domain", "hash", "url", "email"):
        vals = ioc_f1_by_type.get(ioc_type, [])
        mean = sum(vals) / len(vals) if vals else 0.0
        print(f"  {ioc_type:<8}: {mean:.2f}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "export":
        export_gold_set()
    elif len(sys.argv) >= 3 and sys.argv[1] == "run":
        asyncio.run(run_eval(sys.argv[2]))
    else:
        print(__doc__)
