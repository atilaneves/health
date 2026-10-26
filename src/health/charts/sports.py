"""Garmin activities: football, as two charts (heart rates; distance and calories, each on its own
y-axis).

Football was recorded as running until FOOTBALL_SINCE, and nearly always at the Founex pitch, so a
run that starts there is football before that date. From then on football is its own activity type.

VO2max is its own chart: it's Garmin's estimate of fitness, not a measure of one sport, so it takes
every activity that has one (in practice outdoor runs, football at the pitch included). Garmin already
smooths it and rounds it to a whole number, so it's drawn as the value Garmin held on each date, with
no trend of our own on top.
"""

from __future__ import annotations

from datetime import date, timedelta

import plotly.graph_objects as go

from health.charts import style

FOOTBALL_SINCE = date(2026, 10, 22)
FOOTBALL_TYPES = ("soccer", "football")
# The Founex pitch: every run named after Founex starts within ~100 m of here.
PITCH_LAT, PITCH_LON = 46.3411, 6.1695
PITCH_DEG = 0.005  # ~550 m north-south, ~400 m east-west
# Sessions are days apart, not daily like weigh-ins: no 7-day average (it would just be the reading), a
# trend that bends over a month rather than days, and a missed week or two isn't a gap.
TREND_DAYS = 30
GAP_DAYS = 21
TREND_STEP = 7  # a month-scale trend over ten years: weekly points are plenty, and far quicker to draw
DEFAULT_RANGE = "3M"
VO2MAX_RANGE = "1Y"  # a whole number that moves a point every few months: 3 months is a flat line
VO2MAX_CHANGE_DAYS = 365

AT_PITCH = f"abs(lat - {PITCH_LAT}) < {PITCH_DEG} AND abs(lon - {PITCH_LON}) < {PITCH_DEG}"
FOOTBALL = (f"(type = 'running' AND {AT_PITCH} AND ts < DATE '{FOOTBALL_SINCE}') OR "
            f"((type IN {FOOTBALL_TYPES} OR lower(name) LIKE '%football%') AND ts >= DATE '{FOOTBALL_SINCE}')")

# (column, name, unit, format, colour of the readings and their trend, axis title, axis tick format)
HR_AVG = ("avg_hr", "Avg heart rate", "bpm", ".0f", style.RED_LIGHT, "Heart rate (bpm)", ".0f")
HR_MAX = ("max_hr", "Max heart rate", "bpm", ".0f", style.RED, "Heart rate (bpm)", ".0f")
DISTANCE = ("distance_km", "Distance", "km", ".2f", style.AQUA, "Distance (km)", ".1f")
CALORIES = ("calories", "Calories", "kcal", ".0f", style.YELLOW, "Calories (kcal)", ".0f")


def figures(con) -> list[go.Figure]:
    return [_figure(con, "Football: heart rate", FOOTBALL, [(HR_AVG, "y"), (HR_MAX, "y")]),
            _figure(con, "Football: distance and calories", FOOTBALL, [(DISTANCE, "y"), (CALORIES, "y2")]),
            _vo2max(con)]


def _vo2max(con) -> go.Figure:
    pts = con.execute("SELECT ts, vo2max FROM activities WHERE vo2max IS NOT NULL ORDER BY ts").fetchall()
    fig = style.figure("VO2max", "VO2max (ml/kg/min)", height=400)
    if not pts:
        style.subtitle(fig, "no estimates yet")
        return fig
    # No `meta`: the step line is the measure itself, so the tab's checkboxes leave it alone.
    fig.add_scatter(x=[t for t, _ in pts], y=[v for _, v in pts], mode="lines", name="VO2max", hoverinfo="skip",
                    line=dict(color=style.BLUE_DARK, width=2.5, shape="hv"))
    fig.add_scatter(x=[t for t, _ in pts], y=[v for _, v in pts], mode="markers", name="VO2max, estimates",
                    meta="readings", marker=dict(color=style.BLUE, size=6, line=dict(color=style.SURFACE, width=1)),
                    hovertemplate="%{x|%a %d %b %Y}<br><b>%{y:.0f} ml/kg/min</b><extra>VO2max</extra>")
    style.legend(fig)
    text = f"latest {pts[-1][1]:.0f} ml/kg/min"
    then = [v for t, v in pts if t <= pts[-1][0] - timedelta(days=VO2MAX_CHANGE_DAYS)]
    if then:
        text += f" · {pts[-1][1] - then[-1]:+.0f} over the last year"
    style.subtitle(fig, text)
    style.time_range(fig, pts[0][0], pts[-1][0], VO2MAX_RANGE)
    return fig


def _figure(con, title: str, where: str, measures: list[tuple[tuple, str]]) -> go.Figure:
    """`measures` are (measure, axis): "y" on the left, "y2" on the right."""
    fig = style.figure(title, measures[0][0][5], height=400)
    first = last = None
    latest = []
    for (col, name, unit, fmt, color, axis_title, tickformat), axis in measures:
        pts = con.execute(f"SELECT ts, {col} FROM activities WHERE ({where}) AND {col} IS NOT NULL "
                          "ORDER BY ts").fetchall()
        if not pts:
            continue
        n = len(fig.data)
        style.metric(fig, pts, name, color, None, color, unit, fmt, line=color, trend_days=TREND_DAYS, yaxis=axis,
                     avg=False, gap_days=GAP_DAYS, trend_step=TREND_STEP, gl=True)
        # One legend entry per measure, toggling all of its lines; the tab's checkboxes still toggle
        # each kind of line.
        for tr in fig.data[n:]:
            tr.update(legendgroup=name, showlegend=tr.meta == "readings")
        if axis == "y":
            fig.update_yaxes(tickformat=tickformat)
        else:
            fig.update_layout(yaxis2=dict(
                title_text=axis_title, tickformat=tickformat, overlaying="y", side="right", showgrid=False,
                zeroline=False, linecolor=style.GRID, fixedrange=True))
            fig.update_layout(margin=dict(r=72))
        first = min(first or pts[0][0], pts[0][0])
        last = max(last or pts[-1][0], pts[-1][0])
        latest.append(f"{name.lower()} {pts[-1][1]:{fmt}} {unit}")
    if first is None:
        style.subtitle(fig, "no activities yet")
        return fig
    style.legend(fig)
    style.subtitle(fig, "latest " + " · ".join(latest))
    style.time_range(fig, first, last, DEFAULT_RANGE)
    return fig
