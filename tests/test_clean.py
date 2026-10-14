from datetime import date, datetime, timedelta

import pytest

from health.clean import loess, trailing_mean

D = date.fromisoformat


def test_window_is_trailing_seven_calendar_days():
    pts = [(D("2026-10-01"), 70.0), (D("2026-10-04"), 72.0), (D("2026-10-07"), 74.0), (D("2026-10-08"), 76.0)]
    m = dict(trailing_mean(pts))
    assert m[D("2026-10-01")] == 70.0
    assert m[D("2026-10-07")] == pytest.approx(72.0)        # 10-01..10-07
    assert m[D("2026-10-08")] == pytest.approx(74.0)        # 10-01 dropped: 10-02..10-08


def test_isolated_reading_averages_to_itself():
    pts = [(D("2026-01-01"), 70.0), (D("2026-03-01"), 80.0)]
    assert trailing_mean(pts) == pts


def test_timestamps_and_unsorted_input():
    pts = [(datetime(2026, 10, 8, 8), 4.0), (datetime(2026, 10, 1, 9), 2.0), (datetime(2026, 10, 8, 7), 6.0)]
    m = trailing_mean(pts)
    assert [t for t, _ in m] == sorted(t for t, _ in pts)
    # 10-01 09:00 is less than 7 days before 10-08 07:00 and 08:00, so it stays in both windows
    assert m[-1][1] == pytest.approx(4.0)


def test_loess_follows_a_straight_line_away_from_the_edges():
    pts = [(D("2026-01-01") + timedelta(days=i), 70.0 + 0.1 * i) for i in range(0, 60, 3)]
    out = {t.date(): v for t, v in loess(pts, 14)}
    assert out[D("2026-01-31")] == pytest.approx(73.0, abs=0.01)  # symmetric window: no bias


def test_loess_stops_where_too_few_readings():
    pts = [(D("2026-01-01"), 70.0), (D("2026-01-02"), 71.0), (D("2026-01-03"), 72.0), (D("2026-06-01"), 80.0)]
    out = {t.date(): v for t, v in loess(pts, 7)}
    assert out[D("2026-01-02")] is not None
    assert out[D("2026-03-01")] is None and out[D("2026-06-01")] is None


def test_loess_never_extrapolates_past_the_readings():
    # three readings bunched at the start of a window used to fling the line far beyond them
    pts = [(datetime(2026, 1, 1, 8), 120.0), (datetime(2026, 1, 1, 9), 150.0), (datetime(2026, 1, 2, 8), 125.0)]
    vals = [v for _, v in loess(pts, 30) if v is not None]
    assert vals and all(120 <= v <= 150 for v in vals)
    assert all(v is None for t, v in loess(pts, 30) if t.date() > D("2026-01-02"))


def test_loess_does_not_bridge_a_gap_with_no_readings():
    # readings until Aug 21, then from Oct 5: a ±30-day window reaches both sides of mid-September
    pts = [(D("2026-08-01") + timedelta(days=i), 73.0) for i in range(0, 21, 2)]
    pts += [(D("2026-10-05") + timedelta(days=i), 77.0) for i in range(10)]
    out = {t.date(): v for t, v in loess(pts, 30)}
    assert out[D("2026-09-20")] is None
    assert out[D("2026-08-15")] is not None and out[D("2026-08-25")] is None   # past the last reading
    assert out[D("2026-10-08")] is not None
