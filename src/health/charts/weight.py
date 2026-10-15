"""Garmin weight: weigh-ins on a spline, plus the 7-day average."""

from __future__ import annotations

import plotly.graph_objects as go

from health.charts import style


def figure(con) -> go.Figure:
    pts = con.execute("SELECT coalesce(ts, date::TIMESTAMP), weight_kg FROM weigh_ins ORDER BY 1").fetchall()
    fig = style.figure("Weight", "kg")
    if not pts:
        return fig
    means, slope = style.metric(fig, pts, "Weight", style.BLUE, style.BLUE_LIGHT, style.BLUE_DARK, "kg", ".1f",
                                hover_time="%a %d %b %Y")
    style.legend(fig)
    style.subtitle(fig, f"latest {pts[-1][1]:.1f} kg · 7-day avg {means[-1][1]:.1f} kg · "
                        + style.slope_text(slope, "kg", ".2f"))
    style.time_range(fig, pts[0][0], pts[-1][0])
    return fig
