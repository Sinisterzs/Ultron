"""Best-effort approximate location for regional search hints.

The service infers location from this machine's public IP. Only coarse fields
are retained in a short in-process cache; the IP and precise coordinates are
never stored or logged. A failure is intentionally indistinguishable from no
location so search remains usable offline.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request

_ENDPOINT = "https://ipapi.co/json/"
_TIMEOUT_SECONDS = 3.0
_CACHE_SECONDS = 6 * 60 * 60
_lock = threading.Lock()
_cached: tuple[float, dict[str, str] | None] = (0.0, None)


def get_search_location():
    """Confirmed user preference takes precedence over the IP hint."""
    from core.location_preferences import get_override
    manual = get_override()
    if manual:
        return {**manual, 'source': 'manual'}
    approximate = get_approximate_location()
    return {**approximate, 'source': 'ip'} if approximate else None


def get_approximate_location() -> dict[str, str] | None:
    """Return coarse country/region/city/currency, or ``None`` on failure."""
    global _cached
    now = time.monotonic()
    with _lock:
        if now - _cached[0] < _CACHE_SECONDS:
            return dict(_cached[1]) if _cached[1] else None

    try:
        request = urllib.request.Request(
            _ENDPOINT,
            headers={"User-Agent": "ULTRON regional search hint/1"},
        )
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
        location = {
            key: str(payload[key]).strip()
            for key in ("country_name", "country_code", "region", "city", "currency")
            if payload.get(key)
        }
        if not location:
            location = None
    except Exception:
        location = None

    with _lock:
        _cached = (time.monotonic(), location)
    return dict(location) if location else None
