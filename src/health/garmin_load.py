"""raw/garmin JSON -> DuckDB (garmin_daily, garmin_sleep). Idempotent upserts.

All knowledge of Garmin's response shapes lives in the `parse_*` functions below.
Shapes are from long-standing Garmin Connect responses (NOT verified against a live account).
Each parser returns a dict or None (no usable data that day).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from health.garmin_sync import GARMIN_RAW

SCHEMA = """
CREATE TABLE IF NOT EXISTS garmin_daily (
  date DATE PRIMARY KEY, steps INTEGER, resting_hr INTEGER, min_hr INTEGER, max_hr INTEGER,
  avg_stress INTEGER, max_stress INTEGER,
  body_battery_high INTEGER, body_battery_low INTEGER,
  body_battery_charged INTEGER, body_battery_drained INTEGER,
  moderate_min INTEGER, vigorous_min INTEGER,
  calories_total INTEGER, calories_active INTEGER, distance_m DOUBLE, floors DOUBLE);
CREATE TABLE IF NOT EXISTS garmin_sleep (
  wake_date DATE PRIMARY KEY, duration_s INTEGER, deep_s INTEGER, light_s INTEGER,
  rem_s INTEGER, awake_s INTEGER, score INTEGER,
  bed_utc TIMESTAMP, wake_utc TIMESTAMP, bed_local TIMESTAMP, wake_local TIMESTAMP);
"""


def _g(d, *path):
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _ms_utc(ms):
    return None if ms is None else datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)


def _ms_local(ms):
    # Garmin "Local" timestamps are epoch-ms of the wall-clock time as if it were UTC.
    return _ms_utc(ms)


def _int(v):
    return None if v is None else int(round(v))


# ---- field-path isolation: fix shapes here ----------------------------------------------

def parse_stats(stats, rhr=None, body_battery=None, stress=None):
    """stats = get_stats; rhr = get_rhr_day; body_battery = get_body_battery; stress = get_stress_data."""
    if not stats:
        return None
    rhr_v = None
    for row in _g(rhr, "allMetrics", "metricsMap", "WELLNESS_RESTING_HEART_RATE") or []:
        rhr_v = row.get("value", rhr_v)
    bb = (body_battery or [{}])[0] if isinstance(body_battery, list) and body_battery else {}
    return {
        "steps": _int(stats.get("totalSteps")),
        "resting_hr": _int(rhr_v if rhr_v is not None else stats.get("restingHeartRate")),
        "min_hr": _int(stats.get("minHeartRate")),
        "max_hr": _int(stats.get("maxHeartRate")),
        "avg_stress": _int(stats.get("averageStressLevel") if stats.get("averageStressLevel") is not None
                           else _g(stress, "avgStressLevel")),
        "max_stress": _int(stats.get("maxStressLevel") if stats.get("maxStressLevel") is not None
                           else _g(stress, "maxStressLevel")),
        "body_battery_high": _int(stats.get("bodyBatteryHighestValue")),
        "body_battery_low": _int(stats.get("bodyBatteryLowestValue")),
        "body_battery_charged": _int(stats.get("bodyBatteryChargedValue", bb.get("charged"))),
        "body_battery_drained": _int(stats.get("bodyBatteryDrainedValue", bb.get("drained"))),
        "moderate_min": _int(stats.get("moderateIntensityMinutes")),
        "vigorous_min": _int(stats.get("vigorousIntensityMinutes")),
        "calories_total": _int(stats.get("totalKilocalories")),
        "calories_active": _int(stats.get("activeKilocalories")),
        "distance_m": stats.get("totalDistanceMeters"),
        "floors": stats.get("floorsAscended"),
    }


def parse_sleep(sleep):
    """get_sleep_data -> {'dailySleepDTO': {...}}."""
    s = _g(sleep, "dailySleepDTO")
    if not s or not s.get("sleepTimeSeconds"):
        return None
    return {
        "duration_s": _int(s.get("sleepTimeSeconds")),
        "deep_s": _int(s.get("deepSleepSeconds")),
        "light_s": _int(s.get("lightSleepSeconds")),
        "rem_s": _int(s.get("remSleepSeconds")),
        "awake_s": _int(s.get("awakeSleepSeconds")),
        "score": _int(_g(s, "sleepScores", "overall", "value")),
        "bed_utc": _ms_utc(s.get("sleepStartTimestampGMT")),
        "wake_utc": _ms_utc(s.get("sleepEndTimestampGMT")),
        "bed_local": _ms_local(s.get("sleepStartTimestampLocal")),
        "wake_local": _ms_local(s.get("sleepEndTimestampLocal")),
    }


# -----------------------------------------------------------------------------------------


def _read(raw: Path, kind: str, day: str):
    p = raw / kind / f"{day}.json"
    return json.loads(p.read_text()) if p.exists() else None


def _days(raw: Path, kind: str) -> list[str]:
    d = raw / kind
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


def _upsert(con, table: str, key: str, day: str, row: dict) -> None:
    cols = [key, *row]
    con.execute(
        f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        [day, *row.values()],
    )


def load(con, raw: Path = GARMIN_RAW) -> dict[str, int]:
    con.execute(SCHEMA)
    n = {"garmin_daily": 0, "garmin_sleep": 0}
    for day in _days(raw, "stats"):
        row = parse_stats(*(_read(raw, k, day) for k in ("stats", "rhr", "body_battery", "stress")))
        if row:
            _upsert(con, "garmin_daily", "date", day, row)
            n["garmin_daily"] += 1
    for day in _days(raw, "sleep"):
        row = parse_sleep(_read(raw, "sleep", day))
        if row:
            _upsert(con, "garmin_sleep", "wake_date", day, row)
            n["garmin_sleep"] += 1
    return n


if __name__ == "__main__":
    from health.db import connect

    print(load(connect()))
