"""Garmin weigh-ins: cached `get_weigh_ins` fetches -> weigh_ins rows.

Shape verified against a real response (2026-10-14): dailyWeightSummaries[].allWeightMetrics[],
weight in grams, `date` = epoch ms of the local wall-clock time (exact midnight = no time recorded).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from health.garmin.cache import Entry, merge_by_day

# Profile edits, not weigh-ins.
SKIP_SOURCES = {"USER_SETTING", "CHANGE_LOG"}
_DAY_MS = 86_400_000


def daily_summaries(entries: list[Entry]) -> dict[str, dict]:
    return merge_by_day(entries, lambda r: r.get("dailyWeightSummaries") or [], lambda s: s["summaryDate"])


def rows(entries: list[Entry]) -> list[tuple]:
    out = []
    for day, s in daily_summaries(entries).items():
        for m in s.get("allWeightMetrics") or []:
            if m.get("sourceType") in SKIP_SOURCES or m.get("weight") is None:
                continue
            ms = m.get("date")
            ts = (datetime.fromtimestamp(ms / 1000, timezone.utc).replace(tzinfo=None)
                  if ms is not None and ms % _DAY_MS else None)
            out.append((date.fromisoformat(day), ts, m["weight"] / 1000))
    return out
