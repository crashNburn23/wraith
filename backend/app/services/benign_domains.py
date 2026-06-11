"""
Benign-domain set used to reject false-positive IOC extractions.

Combines a hand-curated builtin list with an optional downloaded top-sites
list (Tranco). The downloaded file lives at backend/data/benign_domains.txt
and is refreshed via POST /settings/benign-domains/refresh.
"""
import io
import logging
import zipfile
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

TRANCO_URL = "https://tranco-list.eu/top-1m.csv.zip"
DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "benign_domains.txt"

# Hand-curated: security vendors, infra, big tech, gov, news — never IOCs.
BUILTIN = {
    # Security vendors / research
    "github.com", "virustotal.com", "shodan.io", "any.run", "hybrid-analysis.com",
    "urlscan.io", "abuse.ch", "app.any.run", "tria.ge", "bazaar.abuse.ch",
    "malwarebazaar.abuse.ch", "threatfox.abuse.ch", "feodotracker.abuse.ch",
    "proofpoint.com", "safebreach.com", "crowdstrike.com", "mandiant.com",
    "recordedfuture.com", "team-cymru.com", "shadowserver.org",
    "talosintelligence.com", "talos.com", "unit42.paloaltonetworks.com",
    "paloaltonetworks.com", "checkpoint.com", "sentinelone.com",
    "secureworks.com", "fireeye.com", "huntress.com",
    # Cloud/infra
    "amazonaws.com", "azure.com", "cloudflare.com", "fastly.com",
    "akamai.com", "digitalocean.com", "linode.com",
    # Microsoft / Apple / Google / Amazon
    "microsoft.com", "windows.com", "office.com", "live.com",
    "google.com", "googleapis.com", "gstatic.com", "youtube.com",
    "apple.com", "icloud.com", "amazon.com", "aws.amazon.com",
    # Government / standards
    "cisa.gov", "nist.gov", "nvd.nist.gov", "us-cert.gov", "cve.org",
    "mitre.org", "attack.mitre.org",
    # News / reference
    "exploit-db.com", "bleepingcomputer.com", "theregister.com",
    "techcrunch.com", "wired.com", "darkreading.com", "securityweek.com",
    "bbc.co.uk", "reuters.com", "krebsonsecurity.com", "arstechnica.com",
    # Test/generic
    "example.com", "test.com", "localhost",
}

_file_set: set[str] = set()
_file_mtime: float | None = None


def get_benign_set() -> set[str]:
    """Builtin set plus the downloaded list, reloaded when the file changes."""
    global _file_set, _file_mtime
    try:
        mtime = DATA_FILE.stat().st_mtime
        if mtime != _file_mtime:
            _file_set = {
                line.strip().lower()
                for line in DATA_FILE.read_text().splitlines()
                if line.strip() and not line.startswith("#")
            }
            _file_mtime = mtime
            logger.info("Loaded %d benign domains from %s", len(_file_set), DATA_FILE)
    except FileNotFoundError:
        _file_set = set()
        _file_mtime = None
    return BUILTIN | _file_set


def is_benign_domain(hostname: str) -> bool:
    h = hostname.lower().replace("[", "").replace("]", "").rstrip(".")
    benign = get_benign_set()
    if h in benign:
        return True
    # subdomain membership: a.b.example.com matches example.com
    parts = h.split(".")
    for i in range(1, len(parts) - 1):
        if ".".join(parts[i:]) in benign:
            return True
    return False


async def refresh_from_tranco(top_n: int = 5000) -> int:
    """Download the Tranco top-1M list and store the top N domains locally."""
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resp = await client.get(TRANCO_URL)
        resp.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    name = zf.namelist()[0]
    domains = []
    with zf.open(name) as f:
        for line in io.TextIOWrapper(f, encoding="utf-8"):
            # format: rank,domain
            parts = line.strip().split(",")
            if len(parts) == 2:
                domains.append(parts[1].lower())
            if len(domains) >= top_n:
                break
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        f"# Tranco top-{top_n} — refreshed via /settings/benign-domains/refresh\n"
        + "\n".join(domains) + "\n"
    )
    logger.info("Benign domain list refreshed: %d domains", len(domains))
    return len(domains)
