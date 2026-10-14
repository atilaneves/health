"""Vendor-neutral smoothing over project tables."""

from __future__ import annotations

from collections import deque
from datetime import date, datetime, timedelta

WINDOW_DAYS = 7


def _at(t: date | datetime) -> datetime:
    return t if isinstance(t, datetime) else datetime(t.year, t.month, t.day)


def trailing_mean(points: list[tuple[date | datetime, float]], days: int = WINDOW_DAYS) -> list[tuple[date | datetime, float]]:
    """At each reading, the mean of all readings in the trailing `days` calendar days (inclusive of
    the reading itself). Nothing is interpolated: a reading with no neighbours averages to itself."""
    out, window, total = [], deque(), 0.0
    span = timedelta(days=days)
    for t, v in sorted(points, key=lambda p: _at(p[0])):
        now = _at(t)
        window.append((now, v))
        total += v
        while now - window[0][0] >= span:
            total -= window.popleft()[1]
        out.append((t, total / len(window)))
    return out


def loess(points: list[tuple[date | datetime, float]], half_window_days: float,
          min_points: int = 3, max_gap_days: float = WINDOW_DAYS) -> list[tuple[datetime, float | None]]:
    """Degree-0 LOESS (tricube-weighted local mean), evaluated once per calendar day from the first
    to the last reading.

    Each day's value is the mean of the readings within ±half_window_days, weighted by the tricube of
    their distance in time, so it always stays within the range of those readings. (Local *linear*
    fits overshot badly on this data: a tight cluster on one side sets a steep slope that the
    sparse other side can't hold down.) The value is None unless the window holds at least
    `min_points` readings with some on each side of the day, and the nearest reading is at most
    `max_gap_days` away: otherwise a wide window would bridge a long gap with a curve that has no
    readings under it.
    """
    if not points:
        return []
    pts = sorted((_at(t), v) for t, v in points)
    h = half_window_days * 86400
    day = timedelta(days=1)
    x = pts[0][0].replace(hour=0, minute=0, second=0, microsecond=0)
    out, lo = [], 0
    while x <= pts[-1][0] + day:
        while lo < len(pts) and (x - pts[lo][0]).total_seconds() > h:
            lo += 1
        sw = swy = 0.0
        n = 0
        nearest = float("inf")
        before = after = False
        for t, v in pts[lo:]:
            d = (t - x).total_seconds()
            if d > h:
                break
            w = (1 - (abs(d) / h) ** 3) ** 3
            n += 1
            sw += w
            swy += w * v
            nearest = min(nearest, abs(d))
            before |= d <= 0
            after |= d >= 0
        ok = n >= min_points and sw > 0 and before and after and nearest <= max_gap_days * 86400
        out.append((x, swy / sw if ok else None))
        x += day
    return out
