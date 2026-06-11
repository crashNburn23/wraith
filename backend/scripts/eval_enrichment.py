"""
Enrichment evaluation harness.

Keeps prompt/model changes honest: run a gold set of manually verified
articles through the current enrichment pipeline and diff the extractions.

Usage:
  # 1. Export current enriched articles as a starting gold set (review by hand!)
  .venv/bin/python3 -m scripts.eval_enrichment export > gold_set.json

  # 2. After changing the prompt or model, score against the gold set
  .venv/bin/python3 -m scripts.eval_enrichment run gold_set.json

Gold set format: [{"title", "text", "expected": {"threat_category",
"severity_score", "cves": [], "threat_actors": [], "ioc_values": []}}, ...]
"""
import asyncio
import json
import sys

from app.db.session import SessionLocal
from app.models import Article
from app.services.enrichment_prompt import enrich_article


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
            out.append({
                "title": a.title,
                "text": a.scraped_text[:8000],
                "expected": {
                    "threat_category": a.threat_category,
                    "severity_score": a.ai_severity_score,
                    "cves": [m.cve_id for m in a.cve_mentions],
                    "threat_actors": [aa.actor.name for aa in a.article_actors if aa.actor],
                    "ioc_values": [i.value for i in a.iocs],
                },
            })
        json.dump(out, sys.stdout, indent=2)
        print(f"\n# exported {len(out)} articles — REVIEW AND CORRECT before using as gold", file=sys.stderr)
    finally:
        db.close()


async def run_eval(path: str) -> None:
    gold = json.load(open(path))
    cat_hits = sev_diffs = cve_f1_sum = actor_f1_sum = 0
    n = len(gold)

    def f1(expected: set, got: set) -> float:
        if not expected and not got:
            return 1.0
        if not expected or not got:
            return 0.0
        tp = len(expected & got)
        p = tp / len(got)
        r = tp / len(expected)
        return 2 * p * r / (p + r) if (p + r) else 0.0

    for i, case in enumerate(gold):
        exp = case["expected"]
        try:
            result = await enrich_article(case["title"], case["text"])
        except Exception as e:
            print(f"[{i+1}/{n}] ERROR: {case['title'][:60]} — {e}")
            continue
        cat_ok = result.threat_category == exp.get("threat_category")
        sev_diff = abs((result.severity_score or 0) - (exp.get("severity_score") or 0))
        cves = f1(set(exp.get("cves", [])), set(result.cves))
        actors = f1(
            {a.lower() for a in exp.get("threat_actors", [])},
            {a.lower() for a in result.threat_actors},
        )
        cat_hits += cat_ok
        sev_diffs += sev_diff
        cve_f1_sum += cves
        actor_f1_sum += actors
        print(f"[{i+1}/{n}] cat={'✓' if cat_ok else '✗'} sevΔ={sev_diff:.0f} cveF1={cves:.2f} actorF1={actors:.2f}  {case['title'][:60]}")

    print("\n=== SUMMARY ===")
    print(f"category accuracy : {cat_hits}/{n} ({cat_hits/n:.0%})")
    print(f"mean severity Δ   : {sev_diffs/n:.1f}")
    print(f"mean CVE F1       : {cve_f1_sum/n:.2f}")
    print(f"mean actor F1     : {actor_f1_sum/n:.2f}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "export":
        export_gold_set()
    elif len(sys.argv) >= 3 and sys.argv[1] == "run":
        asyncio.run(run_eval(sys.argv[2]))
    else:
        print(__doc__)
