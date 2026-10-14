"""Recovery charts from DuckDB: resting HR trend, sleep timing."""

from __future__ import annotations

import statistics
from datetime import date, timedelta
from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots

MEAN_WINDOW, MEAN_MIN_DAYS = 7, 5

C_DURATION, C_RHR, C_SLEEP = "#2a6fdb", "#d6453d", "#8a94a6"
LAYOUT = dict(template="plotly_white", hovermode="x unified", margin=dict(l=50, r=50, t=60, b=40),
              font=dict(family="system-ui, sans-serif"))


def _range_selector():
    return dict(buttons=[dict(count=1, label="1m", step="month", stepmode="backward"),
                         dict(count=3, label="3m", step="month", stepmode="backward"),
                         dict(count=6, label="6m", step="month", stepmode="backward"),
                         dict(step="all", label="all")])


def rolling_mean(values: dict[date, float]) -> dict[date, float | None]:
    """Mean of D-6..D per day present, needing >= 5 days. Missing days are never filled."""
    out = {}
    for d in values:
        w = [values[x] for i in range(MEAN_WINDOW) if (x := d - timedelta(days=i)) in values]
        out[d] = statistics.mean(w) if len(w) >= MEAN_MIN_DAYS else None
    return out


def rhr_figure(con) -> go.Figure:
    rows = con.execute("SELECT date, resting_hr FROM garmin_daily WHERE resting_hr IS NOT NULL ORDER BY 1").fetchall()
    rhr = {r[0]: r[1] for r in rows}
    mean7 = rolling_mean(rhr)
    fig = go.Figure()
    fig.add_scatter(x=list(rhr), y=list(rhr.values()), mode="markers", name="Daily",
                    marker=dict(color=C_RHR, size=5, opacity=0.4))
    fig.add_scatter(x=list(mean7), y=list(mean7.values()), mode="lines", name="7-day mean",
                    line=dict(color=C_RHR, width=2.5))
    fig.update_layout(title="Resting heart rate", yaxis_title="bpm", **LAYOUT)
    fig.update_xaxes(rangeselector=_range_selector())
    return fig


def _clock(h: float) -> str:
    h %= 24
    return f"{int(h):02d}:{int(round((h % 1) * 60)) % 60:02d}"


def sleep_figure(con) -> go.Figure:
    rows = con.execute("SELECT wake_date, bed_local, wake_local, duration_s FROM garmin_sleep "
                       "WHERE bed_local IS NOT NULL AND wake_local IS NOT NULL ORDER BY 1").fetchall()
    xs, base, span, dur, hover = [], [], [], [], []
    for wd, bed, wake, d in rows:
        midnight = bed.replace(hour=0, minute=0, second=0, microsecond=0)
        if bed.hour >= 12:  # evening bed time belongs to the previous calendar day
            midnight = midnight + timedelta(days=1)
        b = (bed - midnight).total_seconds() / 3600
        w = (wake - midnight).total_seconds() / 3600
        xs.append(wd); base.append(b); span.append(w - b); dur.append(d / 3600)
        hover.append(f"{_clock(b)} → {_clock(w)}")
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.65, 0.35], vertical_spacing=0.06)
    fig.add_bar(x=xs, y=span, base=base, name="Bed → wake", marker_color=C_SLEEP, opacity=0.8,
                text=hover, hoverinfo="text+x", showlegend=False, row=1, col=1)
    fig.add_bar(x=xs, y=dur, name="Duration (h)", marker_color=C_DURATION, row=2, col=1)
    ticks = list(range(-4, 12, 2))
    fig.update_yaxes(autorange="reversed", tickvals=ticks, ticktext=[_clock(t) for t in ticks],
                     title_text="Clock time", row=1, col=1)
    fig.update_yaxes(title_text="Hours asleep", row=2, col=1)
    fig.update_layout(title="Sleep timing and duration", bargap=0.15, **{**LAYOUT, "hovermode": "x"})
    fig.update_xaxes(rangeselector=_range_selector(), row=1, col=1)
    return fig


def render(con, out: Path) -> Path:
    figs = [rhr_figure(con), sleep_figure(con)]
    parts = [f.to_html(full_html=False, include_plotlyjs="cdn" if i == 0 else False)
             for i, f in enumerate(figs)]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("<!doctype html><html><head><meta charset='utf-8'>"
                   "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                   "<title>Recovery</title><style>body{font-family:system-ui;max-width:1100px;margin:0 auto;padding:8px}"
                   "</style></head><body>" + "".join(parts) + "</body></html>")
    return out
