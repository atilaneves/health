"""Cached raw vendor data -> the project tables (health.schema). Rebuilt from scratch each run."""

from __future__ import annotations

from health import schema
from health.garmin import activities, blood_pressure, weight
from health.garmin.fetch import default_cache
from health.tanita import adapter as tanita
from health.tanita.fetch import latest_export


def _insert(con, table: str, cols: tuple[str, ...], rows: list[tuple]) -> int:
    if rows:
        con.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", rows)
    return len(rows)


def load(con, cache=None, tanita_export=None) -> dict[str, int]:
    cache = cache or default_cache()
    con.execute(schema.SCHEMA)
    n = {
        "weigh_ins": _insert(con, "weigh_ins", schema.WEIGH_INS, weight.rows(cache.entries("weight"))),
        "blood_pressure": _insert(con, "blood_pressure", schema.BLOOD_PRESSURE,
                                  blood_pressure.rows(cache.entries("blood_pressure"))),
        "activities": _insert(con, "activities", schema.ACTIVITIES, activities.rows(cache.entries("activities"))),
        "body_comp": 0,
    }
    export = tanita_export or latest_export()
    if export:
        n["body_comp"] = _insert(con, "body_comp", schema.BODY_COMP, tanita.rows(export))
    return n
