"""Shared chart styling (reference dataviz palette, light surface)."""

from datetime import date, datetime, timedelta

import plotly.graph_objects as go

SURFACE = "#fcfcfb"
INK, INK_2, INK_MUTED = "#0b0b0b", "#52514e", "#8a8984"
GRID = "#ebeae6"
BLUE, BLUE_LIGHT, BLUE_DARK = "#2a78d6", "#86b6ef", "#0d366b"   # slot 1; steps 250 and 700
ORANGE, ORANGE_LIGHT, ORANGE_DARK = "#eb6834", "#f3a785", "#7a2d0f"
TEAL, PURPLE = "#1a9e86", "#8a5cd6"   # straight lines joining the readings (off by default)
# Further categorical slots for charts with several series.
AQUA, YELLOW, VIOLET = "#1baf7a", "#eda100", "#6250d6"
# Heart rates: max a bright red, average a lighter one.
RED, RED_LIGHT = "#e5262b", "#ff6b78"


def figure(title: str, y_title: str, height: int = 360) -> go.Figure:
    fig = go.Figure()
    # The title and subtitle are drawn by the page as HTML above the chart (build._card), where long
    # ones wrap on narrow screens; a Plotly title can't.
    fig.update_layout(
        meta=dict(title=title, subtitle=""), height=height, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=12, color=INK_2),
        margin=dict(l=56, r=24, t=24, b=40), hovermode="closest", showlegend=False,
        hoverlabel=dict(bgcolor="white", bordercolor=GRID, font=dict(color=INK)),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, ticks="outside", tickcolor=GRID)
    # y is refit to the visible x-range by the page script (build.PAGE), so zooming is x-only.
    fig.update_yaxes(title_text=y_title, gridcolor=GRID, zeroline=False, linecolor=GRID, fixedrange=True)
    fig.update_layout(dragmode="zoom")
    return fig


# (label, days back from the latest measurement); "YTD" and "All" are handled specially.
RANGES = [("1W", 7), ("1M", 31), ("3M", 92), ("6M", 183), ("YTD", None), ("1Y", 365), ("2Y", 730), ("5Y", 1826)]
DEFAULT_RANGE = "1M"
# Kalman trend time scale: how fast the slope may change (see clean.kalman_trend). Checked against the
# Tanita readings (38, 2026-07-15 .. 2026-10-26) by maximum likelihood: weight and muscle mass fit best
# at 4, fat kg and fat % at 5 (4 within 0.2 log-likelihood), visceral fat anywhere from 4 to 8. Muscle
# quality's likelihood prefers 2, but 4 predicts each next reading slightly better, so it keeps 4 too.
TREND_DAYS = 4


def time_range(fig: go.Figure, first: date | datetime, last: date | datetime, default: str = DEFAULT_RANGE) -> None:
    """Range buttons anchored on the latest measurement, a range slider, and the initial view (`default`)."""
    first, last = _day(first), _day(last)
    end = last + timedelta(days=3)
    buttons = []
    for label, days in RANGES:
        start = date(last.year, 1, 1) if days is None else last - timedelta(days=days)
        if start > first:
            buttons.append((label, start))
    buttons.append(("All", first - timedelta(days=3)))
    # Open on the default range, or on everything if there's less data than that.
    active = next((i for i, (label, _) in enumerate(buttons) if label == default), len(buttons) - 1)
    fig.update_layout(updatemenus=[dict(
        type="buttons", direction="right", x=0, y=1.0, xanchor="left", yanchor="bottom", pad=dict(t=2, b=4),
        showactive=True, bgcolor="#f0efec", bordercolor=GRID, font=dict(size=11, color=INK_2),
        active=active,
        buttons=[dict(label=label, method="relayout", args=[{"xaxis.range": [start.isoformat(), end.isoformat()]}])
                 for label, start in buttons])])
    fig.update_xaxes(range=[buttons[active][1].isoformat(), end.isoformat()],
                     rangeslider=dict(visible=True, thickness=0.08, bgcolor="#f3f2ee", bordercolor=GRID))
    # Header rows: legend at the very top, range buttons just above the plot.
    fig.update_layout(height=fig.layout.height + 52, margin=dict(t=76))
    _place_legend(fig)


def _day(x: date | datetime) -> date:
    return x.date() if isinstance(x, datetime) else x


def metric(fig: go.Figure, points: list[tuple], name: str, color: str, light: str | None, dark: str, unit: str,
           fmt: str, line: str = TEAL, trend_days: float = TREND_DAYS,
           hover_time: str = "%a %d %b %Y %H:%M", yaxis: str = "y", avg: bool = True,
           gap_days: float | None = None, trend_step: int = 1, gl: bool = False) -> tuple[list[tuple], tuple[float, float]]:
    """Raw readings as dots, optionally joined by straight lines (hidden at first), plus their 7-day
    trailing mean as a spline. The average breaks wherever readings are more than 7 days apart (a 7-day
    average can't span months). Also the Kalman trend, with a ±1σ band where there are readings and a
    dotted line across gaps. Returns the 7-day means and the trend's slope (per day) at the last
    reading, with its σ. `yaxis` puts every trace on another y-axis of a multi-axis chart. `avg=False`
    leaves out the average, for sparse readings where it's just the reading; `gap_days` is how far apart
    readings may be before the trend counts the stretch between them as a gap (default 7). `trend_step`
    draws the trend every that many days rather than daily, for long histories with a slow trend. `gl`
    draws the readings with WebGL: much quicker for hundreds of them, but they don't show in the range
    slider."""
    from health.clean import WINDOW_DAYS, kalman_trend, trailing_mean

    n = len(fig.data)
    means = trailing_mean(points)
    lx, ly = [], []
    for i, (t, v) in enumerate(means):
        if i and (t - means[i - 1][0]).total_seconds() > WINDOW_DAYS * 86400:
            lx.append(None)
            ly.append(None)
        lx.append(t)
        ly.append(v)
    # Each kind is its own legend group (one click toggles just it) and carries `meta` so the page's
    # checkboxes can toggle that kind across every chart on its tab. The joining line goes first so the dots sit on
    # top of it, but last in the legend.
    fig.add_scatter(x=[t for t, _ in points], y=[v for _, v in points], mode="lines", name=f"{name}, line",
                    legendgroup=f"{name} line", meta="line", visible="legendonly", legendrank=1001,
                    line=dict(color=line, width=1.5), hoverinfo="skip")
    fig.add_trace((go.Scattergl if gl else go.Scatter)(
        x=[t for t, _ in points], y=[v for _, v in points], mode="markers", name=name,
        legendgroup=f"{name} readings", meta="readings",
        marker=dict(color=color, size=8, line=dict(color=SURFACE, width=2)),
        hovertemplate=f"%{{x|{hover_time}}}<br><b>%{{y:{fmt}}} {unit}</b><extra>{name}</extra>"))
    if avg:
        fig.add_scatter(x=lx, y=ly, mode="lines", name=f"{name}, 7-day avg", legendgroup=f"{name} avg",
                        meta="avg", connectgaps=False,
                        line=dict(color=light, width=2, dash="dash", shape="spline", smoothing=0.6),
                        hovertemplate=f"%{{x|%d %b %Y}}<br>7-day avg %{{y:{fmt}}} {unit}<extra></extra>")
    kalman, slope = kalman_trend(points, trend_days, gap_days or WINDOW_DAYS)
    if trend_step > 1:  # thin the daily trend, keeping where gaps start and end and the last day
        kalman = [k for i, k in enumerate(kalman) if not i % trend_step or i + 1 == len(kalman)
                  or k[3] != kalman[i - 1][3] or k[3] != kalman[i + 1][3]]
    # Measured stretches get the solid line and the band; gaps get a lighter dotted line joining them.
    kx = [t for t, _, _, _ in kalman]
    ky = [None if gap else v for _, v, _, gap in kalman]
    ksd = [None if gap else sd for _, _, sd, gap in kalman]
    gx, gy = [], []
    for i, (t, v, _, gap) in enumerate(kalman):
        edge = not gap and ((i and kalman[i - 1][3]) or (i + 1 < len(kalman) and kalman[i + 1][3]))
        if gap or edge:
            gx.append(t)
            gy.append(v)
        elif gx and gx[-1] is not None:
            gx.append(None)
            gy.append(None)
    fig.add_scatter(x=kx + kx[::-1], y=[v + sd if v is not None else None for v, sd in zip(ky, ksd)]
                    + [v - sd if v is not None else None for v, sd in zip(ky[::-1], ksd[::-1])],
                    mode="lines", fill="toself", fillcolor=_rgba(color, 0.12), line=dict(width=0),
                    name=f"{name}, trend ±1σ", legendgroup=f"{name} trend", meta="trend",
                    showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=gx, y=gy, mode="lines", connectgaps=False, name=f"{name}, trend across gap",
                    legendgroup=f"{name} trend", meta="trend", showlegend=False,
                    line=dict(color=dark, width=2, dash="dot"),
                    hovertemplate=f"%{{x|%d %b %Y}}<br>Trend %{{y:{fmt}}} {unit} (no readings)<extra></extra>")
    fig.add_scatter(x=kx, y=ky, customdata=ksd, mode="lines",
                    connectgaps=False, name=f"{name}, trend", legendgroup=f"{name} trend", meta="trend",
                    line=dict(color=dark, width=3),
                    hovertemplate=f"%{{x|%d %b %Y}}<br>Trend %{{y:{fmt}}} ± %{{customdata:{fmt}}} {unit}"
                                  "<extra></extra>")
    for tr in fig.data[n:]:
        tr.yaxis = yaxis
    return means, slope


def _rgba(hex_color: str, alpha: float) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def slope_text(slope: tuple[float, float], unit: str, fmt: str) -> str:
    """The trend's slope per week, with its σ, for a subtitle."""
    b, sd = slope[0] * 7, slope[1] * 7
    return f"trend {b:+{fmt}} ± {sd:{fmt}} {unit}/wk"


def legend(fig: go.Figure) -> None:
    """Legend on its own row above the range buttons (rows: legend, range buttons, plot)."""
    fig.update_layout(showlegend=True, legend=dict(orientation="h", x=0, xanchor="left", xref="container",
                                                   y=1, yanchor="top", yref="container", font=dict(color=INK_2),
                                                   bgcolor="rgba(0,0,0,0)", indentation=10))
    _place_legend(fig)


def _place_legend(fig: go.Figure) -> None:
    # Container-relative y must be recomputed whenever the height changes: 8px below the top.
    if fig.layout.showlegend and fig.layout.height:
        fig.update_layout(legend_y=1 - 8 / fig.layout.height)


def subtitle(fig: go.Figure, text: str) -> None:
    fig.update_layout(meta=dict(title=fig.layout.meta["title"], subtitle=text))
