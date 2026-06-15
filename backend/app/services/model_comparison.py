import asyncio

from app.services.enrichment_prompt import enrich_article

_CALL_TIMEOUT = 120  # seconds per LLM call


def _f1(expected: set, got: set) -> float:
    if not expected and not got:
        return 1.0
    if not expected or not got:
        return 0.0
    tp = len(expected & got)
    precision = tp / len(got)
    recall = tp / len(expected)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def article_case(article) -> dict:
    return {
        "id": article.id,
        "title": article.title,
        "text": article.scraped_text,
        "expected": {
            "category": article.threat_category,
            "severity": article.ai_severity_score or 0,
            "actors": {aa.actor.name.lower() for aa in article.article_actors if aa.actor},
            "cves": {m.cve_id for m in article.cve_mentions},
            "ttps": {t.technique_id for t in article.ttp_tags},
            "iocs": {f"{i.ioc_type}:{i.value.lower()}" for i in article.iocs},
            "sectors": {s.lower() for s in article.sector_targets or []},
            "geo_targets": {g.lower() for g in article.geo_targets or []},
        },
    }


def gold_case(case: dict, index: int) -> dict:
    expected = case.get("expected", {})
    iocs = {
        f"{ioc_type}:{value.lower()}"
        for ioc_type, values in expected.get("iocs_by_type", {}).items()
        for value in values
    }
    return {
        "id": f"gold-{index}",
        "title": case["title"],
        "text": case["text"],
        "expected": {
            "category": expected.get("threat_category"),
            "severity": expected.get("severity_score") or 0,
            "actors": {a.lower() for a in expected.get("threat_actors", [])},
            "cves": set(expected.get("cves", [])),
            "ttps": set(expected.get("ttps", [])),
            "iocs": iocs,
            "sectors": {s.lower() for s in expected.get("sector_targets", [])},
            "geo_targets": {g.lower() for g in expected.get("geo_targets", [])},
        },
    }


def score_result(expected: dict, result) -> dict:
    metrics = {
        "category_accuracy": float(result.threat_category == expected["category"]),
        "severity_delta": abs((result.severity_score or 0) - expected["severity"]),
        "actor_f1": _f1(expected["actors"], {a.name.lower() for a in result.threat_actors}),
        "cve_f1": _f1(expected["cves"], {c.cve_id for c in result.cves}),
        "ttp_f1": _f1(expected["ttps"], {t.technique_id for t in result.ttps}),
        "ioc_f1": _f1(expected["iocs"], {f"{i.ioc_type}:{i.value.lower()}" for i in result.iocs}),
        "sector_f1": _f1(expected["sectors"], {s.lower() for s in result.sector_targets}),
        "geo_target_f1": _f1(expected["geo_targets"], {g.lower() for g in result.geo_targets}),
    }
    metrics["quality_score"] = round((
        metrics["category_accuracy"]
        + metrics["actor_f1"]
        + metrics["cve_f1"]
        + metrics["ttp_f1"]
        + metrics["ioc_f1"]
        + metrics["sector_f1"]
        + metrics["geo_target_f1"]
        + max(0, 1 - metrics["severity_delta"] / 100)
    ) / 8, 3)
    return metrics


async def _run_one(title: str, text: str, model: str) -> object:
    return await asyncio.wait_for(
        enrich_article(title, text, model=model),
        timeout=_CALL_TIMEOUT,
    )


async def compare_models(cases: list[dict], models: list[str]) -> dict:
    candidates = {model: {"model": model, "cases": [], "errors": []} for model in models}
    # Run sequentially — Ollama processes one inference at a time, so parallel
    # gather just queues the second call and doubles wall time.
    for case in cases:
        for model in models:
            try:
                result = await _run_one(case["title"], case["text"], model)
            except Exception as exc:
                candidates[model]["errors"].append({"article_id": case["id"], "error": str(exc)})
                continue
            candidates[model]["cases"].append({
                "article_id": case["id"],
                "title": case["title"],
                "metrics": score_result(case["expected"], result),
            })

    for candidate in candidates.values():
        cases = candidate["cases"]
        keys = list(cases[0]["metrics"]) if cases else []
        candidate["metrics"] = {
            key: round(sum(case["metrics"][key] for case in cases) / len(cases), 3)
            for key in keys
        }
        candidate["scored"] = len(cases)
    ranked = sorted(candidates.values(), key=lambda c: c["metrics"].get("quality_score", -1), reverse=True)
    return {"candidates": ranked, "winner": ranked[0]["model"] if ranked and ranked[0]["scored"] else None}
