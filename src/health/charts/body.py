"""Tanita body composition: one chart per measure, readings on a spline plus the 7-day average. Fat kg
comes from Tanita's own weighing (not Garmin's)."""

from __future__ import annotations

import plotly.graph_objects as go

from health.charts import style

# (SQL expression over body_comp, title, unit, format)
MEASURES = [
    ("body_fat_pct * weight_kg / 100", "Fat kg", "kg", ".1f"),
    ("visceral_fat", "Visceral fat", "rating", ".1f"),
    ("muscle_mass_kg", "Muscle mass", "kg", ".1f"),
    ("muscle_quality", "Muscle quality", "score", ".0f"),
    ("body_fat_pct", "Fat %", "%", ".1f"),
]


def figures(con) -> list[go.Figure]:
    out = []
    for expr, title, unit, fmt in MEASURES:
        rows = con.execute(f"SELECT ts, {expr} AS v FROM body_comp WHERE v IS NOT NULL ORDER BY ts").fetchall()
        fig = style.figure(title, unit, height=300)
        if rows:
            means, slope = style.metric(fig, rows, title, style.BLUE, style.BLUE_LIGHT, style.BLUE_DARK, unit, fmt)
            style.legend(fig)
            style.subtitle(fig, f"latest {rows[-1][1]:{fmt}} {unit} · 7-day avg {means[-1][1]:{fmt}} {unit} · "
                                    + style.slope_text(slope, unit, ".2f"))
            style.time_range(fig, rows[0][0], rows[-1][0])
        out.append(fig)
    return out
