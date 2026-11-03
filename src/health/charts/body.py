"""Body: one chart per measure, whatever the source. Each has a main series (readings, 7-day average and
trend); where a DEXA scan measures the same thing, its scans are overlaid as red diamonds. Weight is
Garmin's; the rest are Tanita's, and Fat kg comes from Tanita's own weighing (not Garmin's)."""

from __future__ import annotations

from datetime import datetime, time

import plotly.graph_objects as go

from health.charts import style

# (SQL expression over body_comp, title, unit, format, DEXA column and its name or None). DEXA's lean
# mass is lean soft tissue without bone, the nearest thing to Tanita's muscle mass (which also leaves out
# its bone estimate).
#
# DEXA's visceral fat is a mass, converted here to Tanita's rating. Tanita: 1 point ≈ 10 cm² of visceral
# fat on an MRI slice (support.tanita.eu, "How is visceral fat measured by Tanita"). GE CoreScan
# measures the VAT volume in the android band and reports mass = volume × 0.94 g/cm³ (Kaul et al. 2012,
# Obesity 20:1313). The band runs from the iliac crest up 20% of the way to the skull base: ≈ 10 cm at
# 172 cm tall. So rating ≈ mass / 0.94 / 10 cm / 10 cm². Rough: ±1 cm of band is ±10%, and CoreScan's
# limits of agreement with CT are about ±400 cm³ (±4 points).
VAT_BAND_CM = 10
KG_PER_RATING = 10 * VAT_BAND_CM * 0.94 / 1000   # 10 cm² × band height → cm³ → kg
VAT_RATING = f"visceral_fat_kg / {KG_PER_RATING}"
# The converted rating's ±1σ, as (total, scan, conversion), combined in quadrature:
# - scan: repeatability, 44 g RMS SD between repeat iDXA CoreScan scans (Mellis et al. 2014, overweight
#   group, mean VAT 806 g; the nearest to these scans). Matters scan to scan.
# - conversion, systematic (moves every scan together): ±1 cm of band height (±10%), and the level
#   mismatch: Tanita's reference slice is presumably the umbilicus (~L4–L5, the Japanese standard), the band
#   averages ~L3–L5; adjacent levels differ by ~10% (umbilicus 106 vs L5 95 cm², PMC11200797), so ±15%
#   (a judgement). The 0.94 g/cm³ is CoreScan's own constant, so undoing it adds nothing.
VAT_SCAN_SD = 44 / 0.94 / (10 * VAT_BAND_CM)
VAT_CONVERSION_SD = (0.10 ** 2 + 0.15 ** 2) ** 0.5


def _vat_sd(rating: float) -> tuple[float, float, float]:
    conv = VAT_CONVERSION_SD * rating
    return (VAT_SCAN_SD ** 2 + conv ** 2) ** 0.5, VAT_SCAN_SD, conv


MEASURES = [
    ("body_fat_pct * weight_kg / 100", "Fat kg", "kg", ".1f", ("fat_kg", "DEXA fat")),
    ("visceral_fat", "Visceral fat", "rating", ".1f", (VAT_RATING, "DEXA (converted)")),
    ("muscle_mass_kg", "Muscle mass", "kg", ".1f", ("lean_kg", "DEXA lean mass")),
    ("muscle_quality", "Muscle quality", "score", ".0f", None),
    ("body_fat_pct", "Fat %", "%", ".1f", ("fat_pct", "DEXA fat %")),
]


def figures(con) -> list[go.Figure]:
    """Fat kg, visceral fat, muscle mass, weight, muscle quality, fat %."""
    out = [_measure(con, *m) for m in MEASURES]
    out.insert(3, _weight(con))
    return out


def _scans(con, expr: str) -> list[tuple]:
    """DEXA scans of `expr`, at noon so a scan sits in the middle of its day."""
    return [(datetime.combine(d, time(12)), v) for d, v in con.execute(
        f"SELECT date, {expr} FROM dexa WHERE {expr} IS NOT NULL ORDER BY date").fetchall()]


def _measure(con, expr: str, title: str, unit: str, fmt: str, dexa: tuple | None) -> go.Figure:
    rows = con.execute(f"SELECT ts, {expr} AS v FROM body_comp WHERE v IS NOT NULL ORDER BY ts").fetchall()
    scans = _scans(con, dexa[0]) if dexa else []
    fig = _chart(title, unit, fmt, title, rows, scans, dexa[1] if dexa else "",
                 [_vat_sd(v) for _, v in scans] if title == "Visceral fat" else None)
    if rows and title == "Visceral fat":
        _kg_axis(fig)
    return fig


def _weight(con) -> go.Figure:
    garmin = con.execute("SELECT coalesce(ts, date::TIMESTAMP), weight_kg FROM weigh_ins ORDER BY 1").fetchall()
    return _chart("Weight", "kg", ".1f", "Weight", garmin, [], "",
                  hover_time="%a %d %b %Y")


def _chart(title: str, unit: str, fmt: str, name: str, rows: list[tuple], scans: list[tuple], dexa_name: str,
           sd: list[tuple[float, float, float]] | None = None, hover_time: str = "%a %d %b %Y %H:%M") -> go.Figure:
    """`rows` as the series named `name`, with DEXA `scans` as diamonds."""
    fig = style.figure(title, unit, height=300)
    if not rows:
        return fig
    means, level, slope = style.metric(fig, rows, name, style.BLUE, style.BLUE_LIGHT, style.BLUE_DARK,
                                       unit, fmt, hover_time=hover_time)
    text = (f"latest {rows[-1][1]:{fmt}} {unit} · 7-day avg {means[-1][1]:{fmt}} {unit} · "
            + style.trend_text(level, slope, unit, fmt, ".2f"))
    if scans:
        _dexa(fig, scans, dexa_name, unit, fmt, sd)
        text += f" · last DEXA {scans[-1][1]:{fmt}} {unit} ({scans[-1][0]:%d %b %Y})"
    style.legend(fig)
    style.subtitle(fig, text)
    style.time_range(fig, min([rows[0][0], *(t for t, _ in scans)]), rows[-1][0])
    return fig


def _dexa(fig: go.Figure, scans: list[tuple], name: str, unit: str, fmt: str,
          sd: list[tuple[float, float, float]] | None) -> None:
    """DEXA scans as red diamonds; with `sd` (total, scan, conversion), ±1σ error bars of the total."""
    hover = f"%{{x|%d %b %Y}}<br><b>%{{y:{fmt}}}"
    if sd:
        hover += (f" ± %{{customdata[0]:{fmt}}} {unit}</b><br>scan ± %{{customdata[1]:{fmt}}}, "
                  f"conversion ± %{{customdata[2]:{fmt}}}")
    else:
        hover += f" {unit}</b>"
    fig.add_scatter(x=[t for t, _ in scans], y=[v for _, v in scans], mode="markers", name=name,
                    legendgroup="dexa", meta="dexa",
                    marker=dict(color=style.RED, size=11, symbol="diamond", line=dict(color=style.SURFACE, width=1.5)),
                    error_y=dict(type="data", array=[d[0] for d in sd], color=style.RED, thickness=1.5, width=6)
                    if sd else None,
                    customdata=sd, hovertemplate=hover + f"<extra>{name}</extra>")


def _kg_axis(fig: go.Figure) -> None:
    """A right-hand axis in kg of visceral fat at the DEXA conversion. It has no traces of its own: the page
    script (build.PAGE) keeps its range at the left axis's times `layout.meta.scales` whenever it refits y."""
    fig.update_layout(yaxis2=dict(title_text="DEXA kg", overlaying="y", side="right", showgrid=False,
                                  zeroline=False, fixedrange=True, linecolor=style.GRID, tickformat=".2f"),
                      margin=dict(r=64), meta={**fig.layout.meta, "scales": {"yaxis2": KG_PER_RATING}})
    # An invisible trace so Plotly draws the axis at all (it hides axes with no data).
    fig.add_scatter(x=[], y=[], yaxis="y2", showlegend=False, hoverinfo="skip")
