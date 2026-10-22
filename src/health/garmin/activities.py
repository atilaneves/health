"""Garmin activities: cached `get_activities_by_date` fetches -> activities rows.

Shape verified against a real response (2026-10-22): a list of activities, each with activityId,
activityName, activityType.typeKey, startTimeLocal like '2026-10-20 17:40:09', distance (m),
averageSpeed (m/s), calories (kcal), averageHR and maxHR (missing on some older ones), and
startLatitude/startLongitude, and vO2MaxValue (ml/kg/min, only on outdoor runs).
"""

from __future__ import annotations

from datetime import datetime

from health.garmin.cache import Entry


def merged(entries: list[Entry]) -> list[dict]:
    """One item per activity. Like cache.merge_by_day, each fetch replaces every day in its range,
    but a day may hold several activities."""
    acts: dict[int, dict] = {}
    for e in entries:
        lo, hi = e.start.isoformat(), e.end.isoformat()
        for k in [k for k, a in acts.items() if lo <= a["startTimeLocal"][:10] <= hi]:
            del acts[k]
        for a in e.response or []:
            acts[a["activityId"]] = a
    return sorted(acts.values(), key=lambda a: a["startTimeLocal"])


def rows(entries: list[Entry]) -> list[tuple]:
    return [(datetime.fromisoformat(a["startTimeLocal"]), a["activityType"]["typeKey"], a.get("activityName"),
             a["distance"] / 1000 if a.get("distance") else None,
             a["averageSpeed"] * 3.6 if a.get("averageSpeed") else None, a.get("calories") or None,
             a.get("averageHR"), a.get("maxHR"), a.get("startLatitude"), a.get("startLongitude"),
             a.get("vO2MaxValue"))
            for a in merged(entries)]
