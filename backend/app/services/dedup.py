import hashlib
import re
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "ref", "referrer", "source", "fbclid", "gclid", "mc_cid", "mc_eid",
}


def normalise_url(url: str) -> str:
    parsed = urlparse(url.strip())
    # Strip tracking query params
    qs = {k: v for k, v in parse_qs(parsed.query).items() if k.lower() not in _TRACKING_PARAMS}
    clean = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower().rstrip("/"),
        path=parsed.path.rstrip("/") or "/",
        query=urlencode(qs, doseq=True),
        fragment="",
    )
    return urlunparse(clean)


def url_hash(url: str) -> str:
    return hashlib.sha256(normalise_url(url).encode()).hexdigest()
