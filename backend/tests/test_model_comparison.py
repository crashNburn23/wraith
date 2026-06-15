from types import SimpleNamespace

from app.services.model_comparison import _f1, gold_case, score_result


def test_f1_handles_empty_and_partial_sets():
    assert _f1(set(), set()) == 1.0
    assert _f1({"a"}, set()) == 0.0
    assert round(_f1({"a", "b"}, {"b", "c"}), 2) == 0.5


def test_score_result_compares_structured_fields():
    expected = {
        "category": "APT",
        "severity": 70,
        "actors": {"apt28"},
        "cves": {"CVE-2026-1234"},
        "ttps": {"T1566"},
        "iocs": {"domain:evil.example"},
        "sectors": {"finance"},
        "geo_targets": {"eu"},
    }
    result = SimpleNamespace(
        threat_category="APT",
        severity_score=75,
        threat_actors=[SimpleNamespace(name="APT28")],
        cves=[SimpleNamespace(cve_id="CVE-2026-1234")],
        ttps=[SimpleNamespace(technique_id="T1566")],
        iocs=[SimpleNamespace(ioc_type="domain", value="evil.example")],
        sector_targets=["Finance"],
        geo_targets=["EU"],
    )

    metrics = score_result(expected, result)
    assert metrics["category_accuracy"] == 1
    assert metrics["severity_delta"] == 5
    assert metrics["quality_score"] > 0.9


def test_gold_case_normalises_expected_fields():
    case = gold_case({
        "title": "Case",
        "text": "Body",
        "expected": {
            "threat_category": "APT",
            "severity_score": 70,
            "threat_actors": ["APT28"],
            "iocs_by_type": {"domain": ["EVIL.EXAMPLE"]},
        },
    }, 2)
    assert case["id"] == "gold-2"
    assert case["expected"]["actors"] == {"apt28"}
    assert case["expected"]["iocs"] == {"domain:evil.example"}
