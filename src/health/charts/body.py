"""Tanita body composition: one chart per measure, readings on a spline plus the 7-day average."""

from __future__ import annotations

import plotly.graph_objects as go

from health.charts import style

LOESS_DAYS = 14  # half-width of the LOESS window

MEASURES = [
    ("body_fat_pct", "Body fat", "%", ".1f"),
    ("muscle_mass_kg", "Muscle mass", "kg", ".1f"),
    ("muscle_quality", "Muscle quality", "score", ".0f"),
]


def figures(con) -> list[go.Figure]:
    out = []
    for col, title, unit, fmt in MEASURES:
        rows = con.execute(f"SELECT ts, {col} FROM body_comp WHERE {col} IS NOT NULL ORDER BY ts").fetchall()
        fig = style.figure(title, unit, height=300)
        if rows:
            means = style.metric(fig, rows, title, style.BLUE, style.BLUE_LIGHT, style.BLUE_DARK, unit, fmt, LOESS_DAYS)
            style.legend(fig)
            style.subtitle(fig, f"latest {rows[-1][1]:{fmt}} {unit} · 7-day avg {means[-1][1]:{fmt}} {unit}")
            style.time_range(fig, rows[0][0], rows[-1][0])
        out.append(fig)
    return out
