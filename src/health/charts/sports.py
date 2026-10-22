"""Garmin activities: football and running, each one chart with several measures overlaid, every
measure on its own y-axis (heart rates share one).

Football was recorded as running until FOOTBALL_SINCE, and nearly always at the Founex pitch, so a
run that starts there is football before that date. From then on football is its own activity type;
a run at the pitch is never counted as running either way.
"""

from __future__ import annotations

from datetime import date

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

AT_PITCH = f"abs(lat - {PITCH_LAT}) < {PITCH_DEG} AND abs(lon - {PITCH_LON}) < {PITCH_DEG}"
FOOTBALL = (f"(type = 'running' AND {AT_PITCH} AND ts < DATE '{FOOTBALL_SINCE}') OR "
            f"((type IN {FOOTBALL_TYPES} OR lower(name) LIKE '%football%') AND ts >= DATE '{FOOTBALL_SINCE}')")
RUNNING = f"type = 'running' AND NOT coalesce({AT_PITCH}, false)"

# (column, name, unit, format, axis, colour of the readings and their trend)
HR_AVG = ("avg_hr", "Avg heart rate", "bpm", ".0f", "y", style.RED_LIGHT)
HR_MAX = ("max_hr", "Max heart rate", "bpm", ".0f", "y", style.RED)
DISTANCE = ("distance_km", "Distance", "km", ".2f", "y2", style.AQUA)
CALORIES = ("calories", "Calories", "kcal", ".0f", "y3", style.YELLOW)
SPEED = ("avg_speed_kmh", "Avg speed", "km/h", ".1f", "y4", style.VIOLET)

AXES = {  # axis -> (title, side, tick format)
    "y": ("Heart rate (bpm)", "left", ".0f"),
    "y2": ("Distance (km)", "right", ".1f"),
    "y3": ("Calories (kcal)", "right", ".0f"),
    "y4": ("Speed (km/h)", "left", ".1f"),
}


def figures(con) -> list[go.Figure]:
    return [_figure(con, "Football", FOOTBALL, [HR_AVG, HR_MAX, DISTANCE, CALORIES]),
            _figure(con, "Running", RUNNING, [DISTANCE, SPEED, HR_AVG, HR_MAX, CALORIES])]


def _figure(con, title: str, where: str, measures: list[tuple]) -> go.Figure:
    fig = style.figure(title, AXES["y"][0], height=440)
    first = last = None
    latest = []
    for col, name, unit, fmt, axis, color in measures:
        pts = con.execute(f"SELECT ts, {col} FROM activities WHERE ({where}) AND {col} IS NOT NULL "
                          "ORDER BY ts").fetchall()
        if not pts:
            continue
        n = len(fig.data)
        style.metric(fig, pts, name, color, None, color, unit, fmt, line=color, trend_days=TREND_DAYS, yaxis=axis,
                     avg=False, gap_days=GAP_DAYS, trend_step=TREND_STEP, gl=True)
        # With this many measures, one legend entry per measure, toggling all of its lines; its tab's
        # checkboxes still toggle each kind of line.
        for tr in fig.data[n:]:
            tr.update(legendgroup=name, showlegend=tr.meta == "readings")
        first = min(first or pts[0][0], pts[0][0])
        last = max(last or pts[-1][0], pts[-1][0])
        latest.append(f"{pts[-1][1]:{fmt}} {unit}")
    if first is None:
        style.subtitle(fig, "no activities yet")
        return fig
    used = {tr.yaxis for tr in fig.data}
    # Extra axes sit outside the plot, shifted clear of each other (autoshift).
    for axis in ("y2", "y3", "y4"):
        if axis not in used:
            continue
        text, side, tickformat = AXES[axis]
        fig.update_layout({f"yaxis{axis[1:]}": dict(
            title_text=text, tickformat=tickformat, overlaying="y", side=side, anchor="free", autoshift=True, shift=0 if side == "right"
            else -8, gridcolor=style.GRID, showgrid=False, zeroline=False, linecolor=style.GRID, fixedrange=True)})
    fig.update_layout(margin=dict(l=56 + 64 * ("y4" in used), r=24 + 64 * len(used & {"y2", "y3"})))
    style.legend(fig)
    style.subtitle(fig, "latest " + " · ".join(latest))
    style.time_range(fig, first, last, DEFAULT_RANGE)
    return fig
