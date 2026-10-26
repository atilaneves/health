"""Garmin blood pressure: each reading as a diastolic-to-systolic stick, and each burst of readings as
its average with a ±1 standard error bar, against the ESH home-measurement thresholds.

Readings come in bursts of a few days, months apart, at any time of day, so a trend through them would
be mostly invented across the gaps. Home blood pressure is assessed by averaging a run of readings
(ESH/AHA home monitoring: about a week of morning and evening readings), so each burst is one average.
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime

import plotly.graph_objects as go

from health.charts import style
from health.clean import bursts

BURST_GAP_DAYS = 7  # readings further apart than this start a new burst
# ESH 2023 home-measurement thresholds for hypertension (mmHg); the office ones (140/90) don't apply.
REFERENCES = [(135, "135 systolic (home threshold)"), (85, "85 diastolic")]


def figure(con) -> go.Figure:
    rows = con.execute("SELECT ts, systolic, diastolic FROM blood_pressure ORDER BY ts").fetchall()
    fig = style.figure("Blood pressure", "mmHg", height=400)
    if not rows:
        return fig
    for y, label in REFERENCES:
        fig.add_hline(y=y, line=dict(color=style.INK_MUTED, width=1, dash="dot"),
                      annotation=dict(text=label, font=dict(size=11, color=style.INK_MUTED)),
                      annotation_position="top left")
    # One vertical stick per reading, from diastolic to systolic.
    sx, sy = [], []
    for t, s, d in rows:
        sx += [t, t, None]
        sy += [d, s, None]
    fig.add_scatter(x=sx, y=sy, mode="lines", line=dict(color=style.GRID, width=2), hoverinfo="skip",
                    showlegend=False)
    groups = bursts([(t, (s, d)) for t, s, d in rows], BURST_GAP_DAYS)
    for i, (name, color, dark) in enumerate([("Systolic", style.BLUE, style.BLUE_DARK),
                                             ("Diastolic", style.ORANGE, style.ORANGE_DARK)]):
        fig.add_scatter(x=[r[0] for r in rows], y=[r[1 + i] for r in rows], mode="markers", name=name,
                        legendgroup=f"{name} readings", meta="readings",
                        marker=dict(color=color, size=7, line=dict(color=style.SURFACE, width=2)),
                        hovertemplate=f"%{{x|%a %d %b %Y %H:%M}}<br><b>%{{y}} mmHg</b><extra>{name}</extra>")
        avgs = [_average(g, i) for g in groups]
        fig.add_scatter(x=[a[0] for a in avgs], y=[a[1] for a in avgs], mode="markers", name=f"{name}, burst avg",
                        legendgroup=f"{name} avg", meta="avg",
                        error_y=dict(type="data", array=[a[2] for a in avgs], color=dark, thickness=2, width=6),
                        marker=dict(color=dark, size=12, symbol="diamond", line=dict(color=style.SURFACE, width=1)),
                        customdata=[[a[3], a[4]] for a in avgs],
                        hovertemplate="%{customdata[0]} · %{customdata[1]}<br><b>avg %{y:.0f} ± %{error_y.array:.0f}"
                                      f" mmHg</b><extra>{name}</extra>")
    style.legend(fig)
    (_, s_avg, s_se, dates, n), (_, d_avg, d_se, _, _) = _average(groups[-1], 0), _average(groups[-1], 1)
    spread = f" ± {s_se:.0f}/{d_se:.0f}" if s_se else ""
    style.subtitle(fig, f"latest {rows[-1][1]}/{rows[-1][2]} · last burst ({dates}, {n}) "
                        f"avg {s_avg:.0f}/{d_avg:.0f}{spread} mmHg")
    style.time_range(fig, rows[0][0], rows[-1][0])
    return fig


def _average(group: list[tuple], i: int) -> tuple[datetime, float, float, str, str]:
    """A burst's (mean time, mean, standard error, dates, reading count) for systolic (i=0) or diastolic."""
    vals = [v[i] for _, v in group]
    times = [t for t, _ in group]
    mid = times[0] + (times[-1] - times[0]) / 2
    se = statistics.stdev(vals) / math.sqrt(len(vals)) if len(vals) > 1 else 0.0
    return mid, statistics.mean(vals), se, _dates(times[0], times[-1]), \
        f"{len(vals)} reading{'s' * (len(vals) > 1)}"


def _dates(a: datetime, b: datetime) -> str:
    if a.date() == b.date():
        return f"{a:%-d %b %Y}"
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.day}–{b:%-d %b %Y}"
    return f"{a:%-d %b} – {b:%-d %b %Y}"
