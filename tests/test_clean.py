from datetime import date, datetime, timedelta

import pytest

from health.clean import kalman_trend, trailing_mean

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


def test_kalman_follows_a_noisy_line_to_the_right_edge():
    noise = [0.3, -0.2, 0.1, -0.3, 0.2, -0.1]
    pts = [(D("2026-01-01") + timedelta(days=i), 70.0 - 0.05 * i + noise[i % 6]) for i in range(60)]
    trend, (slope, sd) = kalman_trend(pts, 4)
    assert trend[-1][0] == datetime(2026, 3, 1)  # ends exactly at the last reading
    assert trend[-1][1] == pytest.approx(70.0 - 0.05 * 59, abs=0.2)
    assert slope == pytest.approx(-0.05, abs=2 * sd)
    assert sd > 0


def test_kalman_marks_and_bridges_gaps():
    pts = [(D("2026-01-01") + timedelta(days=i), 70.0) for i in range(5)]
    pts += [(D("2026-03-01") + timedelta(days=i), 72.0) for i in range(5)]
    out = {t.date(): (v, gap) for t, v, _, gap in kalman_trend(pts, 4)[0]}
    assert not out[D("2026-01-03")][1]
    assert out[D("2026-01-20")][1]  # in the gap
    assert out[D("2026-02-25")][1]  # within 7 days of a reading, but only on one side
    bridge = [v for d, (v, gap) in sorted(out.items()) if gap and D("2026-01-10") < d < D("2026-02-20")]
    assert bridge == sorted(bridge) and 70.0 <= bridge[0] and bridge[-1] <= 72.0  # monotone, no bulge


def test_kalman_gap_curve_passes_by_a_lone_reading():
    pts = [(D("2026-01-01") + timedelta(days=i), 70.0) for i in range(5)]
    pts += [(D("2026-02-01"), 75.0)]                                    # alone, mid-gap
    pts += [(D("2026-03-01") + timedelta(days=i), 70.0) for i in range(5)]
    out = {t.date(): v for t, v, _, _ in kalman_trend(pts, 4)[0]}
    assert out[D("2026-02-01")] > 72.0
