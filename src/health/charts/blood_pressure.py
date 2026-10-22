"""Garmin blood pressure: systolic and diastolic on splines with 7-day averages, ESH reference lines."""

from __future__ import annotations

import plotly.graph_objects as go

from health.charts import style

# ESH 2023 office thresholds (mmHg): normal < 130/85, high-normal < 140/90, hypertension >= 140/90.
REFERENCES = [(140, "140 systolic"), (130, "130"), (90, "90 diastolic"), (85, "85")]


def figure(con) -> go.Figure:
    rows = con.execute("SELECT ts, systolic, diastolic, pulse FROM blood_pressure ORDER BY ts").fetchall()
    fig = style.figure("Blood pressure", "mmHg", height=400)
    if not rows:
        return fig
    for y, label in REFERENCES:
        fig.add_hline(y=y, line=dict(color=style.INK_MUTED, width=1, dash="dot"),
                      annotation=dict(text=label, font=dict(size=11, color=style.INK_MUTED)),
                      annotation_position="top left")
    # One vertical stick per reading, from diastolic to systolic.
    sx, sy = [], []
    for t, s, d, _ in rows:
        sx += [t, t, None]
        sy += [d, s, None]
    fig.add_scatter(x=sx, y=sy, mode="lines", line=dict(color=style.GRID, width=2), hoverinfo="skip",
                    showlegend=False)
    sys_avg, sys_slope = style.metric(fig, [(r[0], r[1]) for r in rows], "Systolic", style.BLUE, style.BLUE_LIGHT,
                           style.BLUE_DARK, "mmHg", ".0f", line=style.TEAL)
    dia_avg, dia_slope = style.metric(fig, [(r[0], r[2]) for r in rows], "Diastolic", style.ORANGE, style.ORANGE_LIGHT,
                           style.ORANGE_DARK, "mmHg", ".0f", line=style.PURPLE)
    style.legend(fig)
    last = rows[-1]
    style.subtitle(fig, f"latest {last[1]}/{last[2]} · 7-day avg {sys_avg[-1][1]:.0f}/{dia_avg[-1][1]:.0f} · "
                        f"systolic {style.slope_text(sys_slope, 'mmHg', '.1f')} · "
                        f"diastolic {style.slope_text(dia_slope, 'mmHg', '.1f')}")
    style.time_range(fig, rows[0][0], rows[-1][0])
    return fig
