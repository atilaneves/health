"""On-disk cache of Garmin date-range responses, so repeated runs don't go back over the network.

Each fetch is stored verbatim under <root>/<kind>/<start>_<end>_<fetched>.json, wrapped with the
range it covers and when it was fetched. A fetch is authoritative for its days up to FRESH_DAYS
before it was made; days after that may still change (late syncs, edited entries), so they are
re-fetched once the fetch is no longer from today. Only uncovered days ever go over the network.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

FRESH_DAYS = 3

Fetcher = Callable[[date, date], Any]


@dataclass(frozen=True)
class Entry:
    start: date
    end: date
    fetched_at: datetime
    response: Any

    def settled_until(self, now: datetime) -> date:
        """Last day this fetch is authoritative for at time `now`."""
        if self.fetched_at.astimezone(now.tzinfo).date() == now.date():  # fetched today: all fresh
            return self.end
        return min(self.end, self.fetched_at.date() - timedelta(days=FRESH_DAYS))


def _now() -> datetime:
    return datetime.now().astimezone()


class RangeCache:
    def __init__(self, root: Path, now: Callable[[], datetime] = _now):
        self.root = root
        self.now = now

    def entries(self, kind: str) -> list[Entry]:
        """All cached fetches for `kind`, oldest fetch first."""
        d = self.root / kind
        out = []
        for p in sorted(d.glob("*.json")) if d.is_dir() else []:
            w = json.loads(p.read_text())
            out.append(Entry(date.fromisoformat(w["start"]), date.fromisoformat(w["end"]),
                             datetime.fromisoformat(w["fetched_at"]), w["response"]))
        return sorted(out, key=lambda e: e.fetched_at)

    def missing(self, kind: str, start: date, end: date) -> list[tuple[date, date]]:
        """Sub-ranges of [start, end] not settled by any cached fetch."""
        now = self.now()
        settled = sorted((e.start, u) for e in self.entries(kind) if e.start <= (u := e.settled_until(now)))
        gaps, cur = [], start
        for s, e in settled:
            if e < cur:
                continue
            if s > end:
                break
            if s > cur:
                gaps.append((cur, s - timedelta(days=1)))
            cur = e + timedelta(days=1)
            if cur > end:
                return gaps
        gaps.append((cur, end))
        return gaps

    def get(self, kind: str, start: date, end: date, fetch: Fetcher,
            refresh: bool = False) -> list[Entry]:
        """Fetch whatever isn't settled on disk, then return every cached fetch overlapping
        [start, end], oldest first (so later fetches override earlier ones for shared days)."""
        for s, e in [(start, end)] if refresh else self.missing(kind, start, end):
            self._store(kind, s, e, fetch(s, e))
        return [x for x in self.entries(kind) if x.start <= end and x.end >= start]

    def _store(self, kind: str, start: date, end: date, response: Any) -> None:
        fetched_at = self.now()
        d = self.root / kind
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{start}_{end}_{fetched_at:%Y%m%dT%H%M%S%f}.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"start": start.isoformat(), "end": end.isoformat(),
                                   "fetched_at": fetched_at.isoformat(), "response": response}))
        os.replace(tmp, p)  # a crash mid-write never leaves a half file that looks cached


def merge_by_day(entries: list[Entry], items: Callable[[Any], list[dict]],
                 day_of: Callable[[dict], str]) -> dict[str, dict]:
    """Merge cached fetches into one item per 'YYYY-MM-DD' day.

    Entries are oldest first. Each fetch replaces every day in its range, so an item deleted in
    Garmin disappears once a newer fetch covers that day.
    """
    days: dict[str, dict] = {}
    for e in entries:
        lo, hi = e.start.isoformat(), e.end.isoformat()
        for k in [k for k in days if lo <= k <= hi]:
            del days[k]
        for item in items(e.response or {}):
            days[day_of(item)] = item
    return dict(sorted(days.items()))
