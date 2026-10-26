"""Check charts.style.TREND_DAYS and water as a covariate against the Tanita readings.

    uv run python notebooks/trend_fit.py

1. For each Tanita measure, the maximum-likelihood trend time scale (clean.kalman_trend's
   smoothness_days) over a grid, the log-likelihood of every grid value relative to the best, and the
   one-step-ahead prediction error at the best value and at TREND_DAYS.
2. Water % and hydration (water kg / fat-free mass) as a regressor: y - beta * (x - mean x) follows the
   trend, with beta and the time scale fitted together, tested against beta = 0 by likelihood ratio.
   Fat and muscle are estimated from the same impedance as water, so a fit for them is partly circular;
   weight is the measure the test means something for.

Last run (2026-10-26, 38 readings): weight and muscle mass best at 4, fat kg and fat % at 5, visceral fat
flat over 4-8, muscle quality 2 by likelihood but 4 by prediction; water not significant for weight.
"""

from __future__ import annotations

import math
import statistics as st

import duckdb

from health.charts.style import TREND_DAYS
from health.db import DB_PATH

GRID = [1, 1.5, 2, 3, 4, 5, 6, 8, 10, 14, 20, 30, 45, 60, 100, 200]
MEASURES = {  # name -> SQL expression over body_comp
    "weight": "weight_kg",
    "fat kg": "body_fat_pct * weight_kg / 100",
    "muscle mass": "muscle_mass_kg",
    "fat %": "body_fat_pct",
    "muscle quality": "muscle_quality",
    "visceral fat": "visceral_fat",
}
COVARIATES = {"water %": "body_water_pct", "hydration": "body_water_pct / (100 - body_fat_pct)"}


def fit(ts, ys, s):
    """Concentrated log-likelihood (measurement variance r profiled out) of the local linear trend with
    time scale s days, the one-step-ahead RMSE and the noise sd. Same filter as clean.kalman_trend,
    over the readings only; the first two innovations just pin down the initial level and slope."""
    q = 1 / s ** 4
    m, P = (ys[0], 0.0), ((0.0, 0.0), (0.0, 1.0))
    prev = ts[0]
    terms = []
    for t, v in zip(ts, ys):
        dt = (t - prev).total_seconds() / 86400
        prev = t
        mp = (m[0] + dt * m[1], m[1])
        (a, b), (_, d) = P
        Pp = ((a + 2 * dt * b + dt * dt * d + q * dt ** 3 / 3, b + dt * d + q * dt * dt / 2),
              (b + dt * d + q * dt * dt / 2, d + q * dt))
        sv = Pp[0][0] + 1
        k0, k1 = Pp[0][0] / sv, Pp[1][0] / sv
        e = v - mp[0]
        terms.append((e, sv))
        m = (mp[0] + k0 * e, mp[1] + k1 * e)
        P = ((Pp[0][0] - k0 * Pp[0][0], Pp[0][1] - k0 * Pp[0][1]), (Pp[1][0] - k1 * Pp[0][0], Pp[1][1] - k1 * Pp[0][1]))
    terms = terms[2:]
    n = len(terms)
    r = sum(e * e / sv for e, sv in terms) / n
    ll = -0.5 * (n * math.log(2 * math.pi * r) + sum(math.log(sv) for _, sv in terms) + n)
    return ll, math.sqrt(sum(e * e for e, _ in terms) / n), math.sqrt(r)


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    cols = ", ".join(f"{e} AS \"{k}\"" for k, e in {**MEASURES, **COVARIATES}.items())
    rows = con.execute(f"SELECT ts, {cols} FROM body_comp WHERE weight_kg IS NOT NULL AND body_fat_pct IS NOT NULL "
                       "AND body_water_pct IS NOT NULL ORDER BY ts").fetchall()
    names = [*MEASURES, *COVARIATES]
    ts = [r[0] for r in rows]
    col = {k: [r[1 + i] for r in rows] for i, k in enumerate(names)}
    print(f"{len(rows)} readings, {ts[0]:%Y-%m-%d} .. {ts[-1]:%Y-%m-%d}; TREND_DAYS = {TREND_DAYS}\n")

    print(f"{'measure':15s} best  dLL at {TREND_DAYS:g}  1-step RMSE best / {TREND_DAYS:g}  noise sd")
    for k in MEASURES:
        res = {s: fit(ts, col[k], s) for s in GRID + [TREND_DAYS]}
        best = max(res, key=lambda s: res[s][0])
        print(f"{k:15s} {best:4g}  {res[TREND_DAYS][0] - res[best][0]:8.1f}  "
              f"{res[best][1]:9.3f} / {res[TREND_DAYS][1]:.3f}   {res[best][2]:.3f}")
        print("    dLL by time scale:", " ".join(f"{s:g}:{res[s][0] - res[best][0]:.1f}" for s in GRID))

    print("\nCovariates (2 dLL > 3.84 is p < .05, chi-squared with 1 df):")
    for k in ("weight", "fat kg", "muscle mass"):
        ys = col[k]
        base_ll, base_s = max((fit(ts, ys, s)[0], s) for s in GRID)
        for x in COVARIATES:
            xs = col[x]
            mx, sx = st.mean(xs), st.pstdev(xs)
            betas = [i * st.pstdev(ys) / sx / 10 for i in range(-60, 61)]
            ll, beta, s = max((fit(ts, [y - b * (v - mx) for y, v in zip(ys, xs)], s)[0], b, s)
                              for b in betas for s in GRID)
            noise = fit(ts, [y - beta * (v - mx) for y, v in zip(ys, xs)], s)[2]
            print(f"  {k:11s} ~ {x:9s}: {beta * sx:+.3f} per sd of {x}, time scale {s:g} (vs {base_s:g}), "
                  f"2 dLL {2 * (ll - base_ll):5.2f}, noise sd {fit(ts, ys, base_s)[2]:.3f} -> {noise:.3f}")


if __name__ == "__main__":
    main()
