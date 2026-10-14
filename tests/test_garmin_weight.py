from datetime import date, datetime, timedelta, timezone

from health.garmin import weight
from health.garmin.fetch import LazyClient, fetch
from health.garmin.cache import RangeCache

D = date.fromisoformat


def summary(day: str, grams: float) -> dict:
    # Shape taken from a real get_weigh_ins response (2026-10-14).
    m = {"samplePk": hash(day), "date": 0, "calendarDate": day, "weight": grams, "bmi": None,
         "bodyFat": None, "sourceType": "MANUAL", "timestampGMT": None, "weightDelta": None}
    return {"summaryDate": day, "numOfWeightEntries": 1, "minWeight": grams, "maxWeight": grams,
            "latestWeight": m, "allWeightMetrics": [m]}


class FakeClient:
    def __init__(self, days: dict[str, float]):
        self.days, self.calls = days, []

    def get_weigh_ins(self, start: str, end: str):
        self.calls.append((start, end))
        return {"dailyWeightSummaries": [summary(d, g) for d, g in self.days.items() if start <= d <= end]}


def make_cache(tmp_path, day="2026-10-14"):
    t = [datetime.fromisoformat(f"{day}T12:00:00+00:00")]
    return RangeCache(tmp_path, now=lambda: t[0]), t


def test_no_client_created_when_cache_answers(tmp_path):
    cache, _ = make_cache(tmp_path)
    client = FakeClient({"2026-01-05": 72000.0})
    fetch("weight", D("2026-01-01"), D("2026-06-30"), cache=cache, client=LazyClient(lambda: client))
    created = []
    entries = fetch("weight", D("2026-01-01"), D("2026-06-30"), cache=cache,
                    client=LazyClient(lambda: created.append(1) or client))
    assert created == [] and len(client.calls) == 1
    assert list(weight.daily_summaries(entries)) == ["2026-01-05"]


def test_one_client_for_several_gaps(tmp_path):
    cache, _ = make_cache(tmp_path)
    client = FakeClient({})
    fetch("weight", D("2026-03-01"), D("2026-03-31"), cache=cache, client=LazyClient(lambda: client))
    created = []
    fetch("weight", D("2026-02-01"), D("2026-04-30"), cache=cache,
          client=LazyClient(lambda: created.append(1) or client))
    assert created == [1] and len(client.calls) == 3


def test_newer_fetch_overrides_and_deletes(tmp_path):
    cache, t = make_cache(tmp_path)
    client = FakeClient({"2026-10-12": 72000.0, "2026-10-13": 72500.0})
    fetch("weight", D("2026-10-01"), D("2026-10-14"), cache=cache, client=LazyClient(lambda: client))
    # next day: the 10-13 entry was edited, the 10-12 entry deleted in Garmin
    t[0] += timedelta(days=1)
    client.days = {"2026-10-13": 72300.0}
    days = weight.daily_summaries(
        fetch("weight", D("2026-10-01"), D("2026-10-15"), cache=cache, client=LazyClient(lambda: client)))
    assert list(days) == ["2026-10-13"]
    assert days["2026-10-13"]["latestWeight"]["weight"] == 72300.0
