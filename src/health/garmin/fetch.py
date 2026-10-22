"""Cached Garmin date-range fetches (raw/garmin/<kind>/).

    uv run python -m health.garmin.fetch [KIND ...] [--since YYYY-MM-DD] [--refresh]

Each kind is one Garmin endpoint that takes (start, end), so any range is a single request.
After the first run, only days not yet settled on disk go over the network (see health.garmin.cache).
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import date
from typing import Any

from health.db import RAW_DIR
from health.garmin.cache import Entry, RangeCache

# kind -> garminconnect method taking ('YYYY-MM-DD', 'YYYY-MM-DD')
KINDS = {
    "weight": "get_weigh_ins",
    "blood_pressure": "get_blood_pressure",
    "activities": "get_activities_by_date",
}
HISTORY_START = date(2008, 1, 1)  # before Garmin Connect existed, so "everything"


def default_cache() -> RangeCache:
    return RangeCache(RAW_DIR / "garmin")


class LazyClient:
    """Creates the Garmin client on first use only. Even loading saved tokens can refresh them over
    the network, so nothing touches Garmin when the cache can answer."""

    def __init__(self, factory: Callable[[], Any] | None = None):
        self._factory = factory
        self._client = None

    def __getattr__(self, name: str):
        if self._client is None:
            if self._factory is None:
                from health.garmin.auth import get_client
                self._factory = get_client
            self._client = self._factory()
        return getattr(self._client, name)


def fetch(kind: str, start: date = HISTORY_START, end: date | None = None, *, refresh: bool = False,
          cache: RangeCache | None = None, client: Any = None) -> list[Entry]:
    method = KINDS[kind]
    client = client if client is not None else LazyClient()
    cache = cache or default_cache()
    return cache.get(kind, start, end or date.today(),
                     lambda s, e: getattr(client, method)(s.isoformat(), e.isoformat()), refresh=refresh)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="health.garmin.fetch")
    p.add_argument("kinds", nargs="*", metavar="KIND", help=f"one or more of {', '.join(KINDS)} (default: all)")
    p.add_argument("--since", type=date.fromisoformat, default=HISTORY_START)
    p.add_argument("--refresh", action="store_true", help="ignore the cache and re-fetch the range")
    a = p.parse_args(argv)
    if unknown := set(a.kinds) - set(KINDS):
        p.error(f"unknown kind(s): {', '.join(sorted(unknown))}")
    cache, client = default_cache(), LazyClient()
    for kind in a.kinds or KINDS:
        before = len(cache.entries(kind))
        entries = fetch(kind, a.since, refresh=a.refresh, cache=cache, client=client)
        print(f"{kind}: {len(cache.entries(kind)) - before} network request(s), {len(entries)} cached fetch(es)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
