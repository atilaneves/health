"""Vendor-neutral smoothing over project tables."""

from __future__ import annotations

import math
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


def bursts(points: list[tuple], gap_days: float) -> list[list[tuple]]:
    """Readings (time first) split wherever two in a row are more than `gap_days` apart, in time order."""
    out = []
    for p in sorted(points, key=lambda p: _at(p[0])):
        if not out or (_at(p[0]) - _at(out[-1][-1][0])).total_seconds() > gap_days * 86400:
            out.append([])
        out[-1].append(p)
    return out


def kalman_trend(points: list[tuple[date | datetime, float]], smoothness_days: float,
                 max_gap_days: float = WINDOW_DAYS) -> tuple[list[tuple[datetime, float, float, bool]],
                                                             tuple[float, float]]:
    """Local linear trend: a level whose slope drifts as a random walk in continuous time, seen through
    measurement noise, fitted by a Kalman filter and Rauch–Tung–Striebel smoother. Irregular spacing and
    gaps need no special handling: uncertainty simply grows with the time since the last reading.

    `smoothness_days` sets how fast the trend may bend: the slope's drift variance is the measurement
    variance divided by smoothness_days⁴ (as with a smoothing spline, that ratio sets the time scale).
    The measurement variance itself is fitted to the data by maximum likelihood.

    Returns (time, level, standard deviation of level, in_gap) once per calendar day from the first
    reading, ending exactly at the last reading (where the smoothed state is the filtered "trend now").
    in_gap is true unless there's a reading within `max_gap_days` on each side: there nothing is
    measured, and the level is a monotone cubic joining the trend either side. Also returns the slope at the last reading
    and its standard deviation, both per day.
    """
    if not points:
        return [], (0.0, 0.0)
    pts = sorted((_at(t), v) for t, v in points)
    obs_times = [t for t, _ in pts]
    day = timedelta(days=1)
    grid, x = [], obs_times[0].replace(hour=0, minute=0, second=0, microsecond=0) + day
    while x < obs_times[-1]:
        grid.append(x)
        x += day
    # Readings first, so the last event is the last reading. Every variance below is in units of the
    # measurement variance r, fitted afterwards from the innovations (the likelihood concentrates on r).
    events = sorted([(t, v) for t, v in pts] + [(g, None) for g in grid], key=lambda e: (e[0], e[1] is None))
    q = 1 / smoothness_days ** 4
    m, P = (pts[0][1], 0.0), ((1.0, 0.0), (0.0, 1.0))  # vague initial slope
    prev = events[0][0]
    filt, pred, steps, sq_innov = [], [], [], []
    for t, v in events:
        dt = (t - prev).total_seconds() / 86400
        prev = t
        mp = (m[0] + dt * m[1], m[1])
        (a, b), (_, d) = P
        Pp = ((a + 2 * dt * b + dt * dt * d + q * dt ** 3 / 3, b + dt * d + q * dt * dt / 2),
              (b + dt * d + q * dt * dt / 2, d + q * dt))
        if v is not None:
            s = Pp[0][0] + 1
            k0, k1 = Pp[0][0] / s, Pp[1][0] / s
            e = v - mp[0]
            sq_innov.append(e * e / s)
            m = (mp[0] + k0 * e, mp[1] + k1 * e)
            P = ((Pp[0][0] - k0 * Pp[0][0], Pp[0][1] - k0 * Pp[0][1]),
                 (Pp[1][0] - k1 * Pp[0][0], Pp[1][1] - k1 * Pp[0][1]))
        else:
            m, P = mp, Pp
        filt.append((m, P))
        pred.append((mp, Pp))
        steps.append(dt)
    tail = sq_innov[2:] or sq_innov  # the first two only pin down the initial level and slope
    r = sum(tail) / len(tail)
    # RTS smoother, backwards; the level, its variance and the slope are kept for every event.
    sm, sP = filt[-1]
    out = [(events[-1][0], sm[0], math.sqrt(r * sP[0][0]), sm[1])]
    end_slope = (sm[1], math.sqrt(r * sP[1][1]))
    for i in range(len(events) - 2, -1, -1):
        (fm, fP), (pm, pP), dt = filt[i], pred[i + 1], steps[i + 1]
        det = pP[0][0] * pP[1][1] - pP[0][1] * pP[1][0]
        inv = ((pP[1][1] / det, -pP[0][1] / det), (-pP[1][0] / det, pP[0][0] / det))
        fPF = ((fP[0][0] + dt * fP[0][1], fP[0][1]), (fP[1][0] + dt * fP[1][1], fP[1][1]))  # fP @ Fᵀ
        C = tuple(tuple(fPF[j][0] * inv[0][c] + fPF[j][1] * inv[1][c] for c in range(2)) for j in range(2))
        dm = (sm[0] - pm[0], sm[1] - pm[1])
        dP = ((sP[0][0] - pP[0][0], sP[0][1] - pP[0][1]), (sP[1][0] - pP[1][0], sP[1][1] - pP[1][1]))
        sm = (fm[0] + C[0][0] * dm[0] + C[0][1] * dm[1], fm[1] + C[1][0] * dm[0] + C[1][1] * dm[1])
        sP = _full_cov(fP, C, dP)
        out.append((events[i][0], sm[0], math.sqrt(max(r * sP[0][0], 0.0)), sm[1]))
    out.reverse()
    gap = timedelta(days=max_gap_days)
    j = 0
    trend = []
    for t, level, sd, _ in out:
        while j + 1 < len(obs_times) and obs_times[j + 1] <= t:
            j += 1
        before = obs_times[j] <= t and t - obs_times[j] <= gap
        after = any(t <= o <= t + gap for o in obs_times[j:j + 2])
        trend.append((t, level, sd, not (before and after)))
    # Across a gap the smoother carries the slope from either side into it and can bulge well past
    # both ends, so the level there is redrawn as a monotone cubic between anchors: the trend either
    # side, and the trend at any lone reading inside the gap.
    anchor = [not g or (k < len(events) and events[k][1] is not None) for k, (_, _, _, g) in enumerate(trend)]
    i = 0
    while i < len(trend):
        if anchor[i]:
            i += 1
            continue
        k = i
        while k < len(trend) and not anchor[k]:
            k += 1
        if i > 0 and k < len(trend):
            (t0, y0, _, _), (t1, y1, _, _) = trend[i - 1], trend[k]
            for n in range(i, k):
                t, _, sd, _ = trend[n]
                trend[n] = (t, _monotone_cubic(t0, y0, out[i - 1][3], t1, y1, out[k][3], t), sd, True)
        i = k
    # Readings are only needed as anchors: keep one point per day, plus the last reading.
    trend = [p for k, p in enumerate(trend) if events[k][1] is None or k == len(trend) - 1]
    return trend, end_slope


def _monotone_cubic(t0: datetime, y0: float, m0: float, t1: datetime, y1: float, m1: float, t: datetime) -> float:
    """Cubic Hermite from (t0, y0) with slope m0 to (t1, y1) with slope m1 (per day), evaluated at t. The
    end slopes are limited as Fritsch and Carlson do, so the curve stays between y0 and y1."""
    h = (t1 - t0).total_seconds() / 86400
    d = (y1 - y0) / h
    if d == 0 or m0 * d <= 0:
        m0 = 0.0
    if d == 0 or m1 * d <= 0:
        m1 = 0.0
    if d:
        a, b = m0 / d, m1 / d
        if a * a + b * b > 9:
            tau = 3 / math.hypot(a, b)
            m0, m1 = tau * a * d, tau * b * d
    s = (t - t0).total_seconds() / 86400 / h
    return ((2 * s ** 3 - 3 * s ** 2 + 1) * y0 + (s ** 3 - 2 * s ** 2 + s) * h * m0
            + (-2 * s ** 3 + 3 * s ** 2) * y1 + (s ** 3 - s ** 2) * h * m1)


def _full_cov(fP, C, dP):
    """fP + C·dP·Cᵀ for 2×2 matrices given as nested tuples."""
    CdP = tuple(tuple(C[j][0] * dP[0][c] + C[j][1] * dP[1][c] for c in range(2)) for j in range(2))
    return tuple(tuple(fP[j][c] + CdP[j][0] * C[c][0] + CdP[j][1] * C[c][1] for c in range(2)) for j in range(2))
