"""Garmin blood pressure: cached `get_blood_pressure` fetches -> blood_pressure rows.

Shape verified against a real response (2026-10-14): measurementSummaries[] (one per day,
keyed by startDate) each holding measurements[] with systolic, diastolic, pulse (optional) and
measurementTimestampLocal like '2026-05-14T18:32:18.0'.
"""

from __future__ import annotations

from datetime import datetime

from health.garmin.cache import Entry, merge_by_day


def rows(entries: list[Entry]) -> list[tuple]:
    days = merge_by_day(entries, lambda r: r.get("measurementSummaries") or [], lambda s: s["startDate"])
    return [(datetime.fromisoformat(m["measurementTimestampLocal"]), m["systolic"], m["diastolic"], m.get("pulse"))
            for s in days.values() for m in s.get("measurements") or []
            if m.get("systolic") is not None and m.get("diastolic") is not None]
