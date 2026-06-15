"""
ATT&CK technique validation and actor-name tracking-ID filtering.

Technique list is loaded from data/attack_techniques.json (bundled from MITRE CTI).
Falls back to accept-all if the file is missing so enrichment is never blocked.
"""
import re
from functools import lru_cache
from pathlib import Path

_DATA_FILE = Path(__file__).parents[2] / "data" / "attack_techniques.json"

# Patterns that indicate a tracking identifier rather than a threat actor name
_TRACKING_PATTERNS = [
    re.compile(r"^[A-Za-z][\w]+-\d{4}-\d+$"),      # Sonatype-2026-003775, GHSA-xxxx-xxxx-xxxx
    re.compile(r"^UNK_", re.IGNORECASE),              # UNK_DeadDrop, UNK_*
    re.compile(r"^CVE-\d{4}-\d+$", re.IGNORECASE),   # CVE IDs in the wrong field
    re.compile(r"^GHSA-", re.IGNORECASE),             # GitHub Security Advisory IDs
    re.compile(r"^[A-Z]{2,}-\d{4,}$"),               # All-caps code + digits (e.g. MAL-12345)
]


@lru_cache(maxsize=1)
def _load_techniques() -> frozenset:
    try:
        import json
        return frozenset(json.loads(_DATA_FILE.read_text()))
    except Exception:
        return frozenset()


def is_valid_technique(tid: str) -> bool:
    valid = _load_techniques()
    if not valid:
        return True  # graceful fallback: accept all if data file missing
    return tid in valid


def is_tracking_actor_name(name: str) -> bool:
    return any(p.search(name) for p in _TRACKING_PATTERNS)


def filter_ttps(ttps: list) -> list:
    """Drop TTPs with invalid technique IDs. Accepts dicts or ORM objects."""
    out = []
    for ttp in ttps:
        tid = ttp.technique_id if hasattr(ttp, "technique_id") else ttp.get("technique_id", "")
        if is_valid_technique(tid):
            out.append(ttp)
    return out


def filter_actors(actors: list) -> list:
    """Drop actors whose names look like tracking identifiers."""
    out = []
    for actor in actors:
        name = actor.name if hasattr(actor, "name") else actor.get("name", "")
        if name and not is_tracking_actor_name(name):
            out.append(actor)
    return out
