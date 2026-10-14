from datetime import date, datetime, timedelta, timezone

import pytest

from health.garmin.cache import FRESH_DAYS, RangeCache

D = date.fromisoformat


class Clock:
    def __init__(self, day: str):
        self.t = datetime.fromisoformat(f"{day}T12:00:00+00:00")

    def __call__(self):
        return self.t

    def advance(self, days: int = 0, hours: float = 0):
        self.t += timedelta(days=days, hours=hours)


class Fetcher:
    def __init__(self):
        self.calls: list[tuple[date, date]] = []

    def __call__(self, start, end):
        self.calls.append((start, end))
        return {"range": [start.isoformat(), end.isoformat()], "n": len(self.calls)}


@pytest.fixture
def clock():
    return Clock("2026-10-14")


@pytest.fixture
def cache(tmp_path, clock):
    return RangeCache(tmp_path, now=clock)


def test_first_get_fetches_whole_range(cache):
    f = Fetcher()
    entries = cache.get("weight", D("2026-01-01"), D("2026-10-14"), f)
    assert f.calls == [(D("2026-01-01"), D("2026-10-14"))]
    assert [e.response["n"] for e in entries] == [1]


def test_repeat_get_same_day_hits_disk_only_for_settled_days(cache):
    f = Fetcher()
    cache.get("weight", D("2026-01-01"), D("2026-10-10"), f)
    f.calls.clear()
    cache.get("weight", D("2026-01-01"), D("2026-10-10"), f)
    # fetched on 10-14: everything up to 10-11 is settled, so 10-01..10-10 needs nothing
    assert f.calls == []


def test_fetch_from_today_answers_everything(cache, clock):
    f = Fetcher()
    cache.get("weight", D("2026-01-01"), D("2026-10-14"), f)
    clock.advance(hours=11)  # 23:00, still the same day
    f.calls.clear()
    cache.get("weight", D("2026-01-01"), D("2026-10-14"), f)
    assert f.calls == []


def test_recent_days_are_refetched_the_next_day(cache, clock):
    f = Fetcher()
    cache.get("weight", D("2026-01-01"), D("2026-10-14"), f)
    clock.advance(hours=13)  # 01:00 the next day
    f.calls.clear()
    cache.get("weight", D("2026-01-01"), D("2026-10-14"), f)
    settled = D("2026-10-14") - timedelta(days=FRESH_DAYS)
    assert f.calls == [(settled + timedelta(days=1), D("2026-10-14"))]


def test_next_day_fetches_only_the_tail(cache, clock):
    f = Fetcher()
    cache.get("weight", D("2016-01-01"), D("2026-10-14"), f)
    clock.advance(1)
    f.calls.clear()
    cache.get("weight", D("2016-01-01"), D("2026-10-15"), f)
    assert f.calls == [(D("2026-10-12"), D("2026-10-15"))]


def test_gaps_on_both_sides_are_fetched_separately(cache):
    f = Fetcher()
    cache.get("weight", D("2026-03-01"), D("2026-03-31"), f)
    f.calls.clear()
    cache.get("weight", D("2026-02-01"), D("2026-04-30"), f)
    assert f.calls == [(D("2026-02-01"), D("2026-02-28")), (D("2026-04-01"), D("2026-04-30"))]


def test_refresh_bypasses_cache(cache):
    f = Fetcher()
    cache.get("weight", D("2026-01-01"), D("2026-06-30"), f)
    f.calls.clear()
    cache.get("weight", D("2026-01-01"), D("2026-06-30"), f, refresh=True)
    assert f.calls == [(D("2026-01-01"), D("2026-06-30"))]


def test_entries_oldest_fetch_first_and_persist(tmp_path, clock):
    f = Fetcher()
    RangeCache(tmp_path, now=clock).get("weight", D("2026-01-01"), D("2026-10-14"), f)
    clock.advance(1)
    entries = RangeCache(tmp_path, now=clock).get("weight", D("2026-01-01"), D("2026-10-15"), f)
    assert [e.response["n"] for e in entries] == [1, 2]
    assert entries[0].fetched_at < entries[1].fetched_at


def test_entries_outside_requested_range_are_not_returned(cache):
    f = Fetcher()
    cache.get("weight", D("2025-01-01"), D("2025-12-31"), f)
    entries = cache.get("weight", D("2026-01-01"), D("2026-01-31"), f)
    assert [e.start for e in entries] == [D("2026-01-01")]


def test_failed_fetch_stores_nothing(cache):
    def boom(start, end):
        raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        cache.get("weight", D("2026-01-01"), D("2026-01-31"), boom)
    assert cache.entries("weight") == []


def test_kinds_are_independent(cache):
    f = Fetcher()
    cache.get("weight", D("2026-01-01"), D("2026-01-31"), f)
    f.calls.clear()
    cache.get("sleep", D("2026-01-01"), D("2026-01-31"), f)
    assert len(f.calls) == 1
