from datetime import date, datetime

import duckdb

from health import schema
from health.charts import sports
from health.garmin import activities
from health.garmin.cache import Entry
from health.load import _insert

D = date.fromisoformat
FOUNEX = (46.3412, 6.1694)
GENEVA = (46.2090, 6.1498)


def act(id_: int, start: str, type_: str = "running", name: str = "Running", at=GENEVA) -> dict:
    # Shape taken from a real get_activities_by_date response (2026-10-22).
    return {"activityId": id_, "activityName": name, "activityType": {"typeKey": type_}, "startTimeLocal": start,
            "distance": 5000.0, "averageSpeed": 2.5, "calories": 400.0, "averageHR": 150.0, "maxHR": 175.0,
            "startLatitude": at[0], "startLongitude": at[1]}


def entry(start: str, end: str, fetched: str, acts: list[dict]) -> Entry:
    return Entry(D(start), D(end), datetime.fromisoformat(fetched), acts)


def test_newer_fetch_replaces_its_days_but_keeps_several_per_day():
    old = entry("2026-01-01", "2026-01-31", "2026-01-31T12:00:00",
                [act(1, "2026-01-05 10:00:00"), act(2, "2026-01-20 10:00:00")])
    new = entry("2026-01-18", "2026-01-31", "2026-02-01T12:00:00",
                [act(3, "2026-01-20 09:00:00"), act(4, "2026-01-20 18:00:00")])
    assert [a["activityId"] for a in activities.merged([old, new])] == [1, 3, 4]


def test_units():
    (row,) = activities.rows([entry("2026-01-01", "2026-01-31", "2026-01-31T12:00:00",
                                    [act(1, "2026-01-05 10:00:00")])])
    assert row[3:7] == (5.0, 9.0, 400.0, 150.0)


def test_football_is_founex_running_until_its_own_type_then_never_running():
    con = duckdb.connect()
    con.execute(schema.SCHEMA)
    acts = [act(1, "2026-10-01 19:00:00", at=FOUNEX),            # football, recorded as running
            act(2, "2026-10-02 18:00:00"),                        # a run
            act(3, "2026-10-29 19:00:00", "soccer", "Football", at=FOUNEX),
            act(4, "2026-10-30 19:00:00", at=FOUNEX),            # a run at the pitch: neither
            act(5, "2026-10-31 07:00:00", at=(None, None))]       # treadmill-like, no position: a run
    _insert(con, "activities", schema.ACTIVITIES,
            activities.rows([entry("2026-10-01", "2026-10-31", "2026-10-31T12:00:00", acts)]))
    q = "SELECT ts::DATE FROM activities WHERE {} ORDER BY ts"
    assert [r[0] for r in con.execute(q.format(sports.FOOTBALL)).fetchall()] == [D("2026-10-01"), D("2026-10-29")]
    assert [r[0] for r in con.execute(q.format(sports.RUNNING)).fetchall()] == [D("2026-10-02"), D("2026-10-31")]
