"""Shared chart styling (reference dataviz palette, light surface)."""

from datetime import date, datetime, timedelta

import plotly.graph_objects as go

SURFACE = "#fcfcfb"
INK, INK_2, INK_MUTED = "#0b0b0b", "#52514e", "#8a8984"
GRID = "#ebeae6"
BLUE, BLUE_LIGHT, BLUE_DARK = "#2a78d6", "#86b6ef", "#0d366b"   # slot 1; steps 250 and 700
ORANGE, ORANGE_LIGHT, ORANGE_DARK = "#eb6834", "#f3a785", "#7a2d0f"


def figure(title: str, y_title: str, height: int = 360) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title=dict(text=title, x=0, xanchor="left", xref="container", y=1, yanchor="top", yref="container",
                   pad=dict(t=14, l=16), font=dict(size=16, color=INK)),
        height=height, paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=12, color=INK_2),
        margin=dict(l=56, r=24, t=56, b=40), hovermode="closest", showlegend=False,
        hoverlabel=dict(bgcolor="white", bordercolor=GRID, font=dict(color=INK)),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, ticks="outside", tickcolor=GRID)
    # y is refit to the visible x-range by the page script (build.PAGE), so zooming is x-only.
    fig.update_yaxes(title_text=y_title, gridcolor=GRID, zeroline=False, linecolor=GRID, fixedrange=True)
    fig.update_layout(dragmode="zoom")
    return fig


# (label, days back from the latest measurement); "YTD" and "All" are handled specially.
RANGES = [("1W", 7), ("1M", 31), ("3M", 92), ("6M", 183), ("YTD", None), ("1Y", 365), ("2Y", 730), ("5Y", 1826)]


def time_range(fig: go.Figure, first: date | datetime, last: date | datetime) -> None:
    """Range buttons anchored on the latest measurement, a range slider, and the initial view."""
    first, last = _day(first), _day(last)
    end = last + timedelta(days=3)
    buttons = []
    for label, days in RANGES:
        start = date(last.year, 1, 1) if days is None else last - timedelta(days=days)
        if start > first:
            buttons.append((label, start))
    buttons.append(("All", first - timedelta(days=3)))
    fig.update_layout(updatemenus=[dict(
        type="buttons", direction="right", x=0, y=1.0, xanchor="left", yanchor="bottom", pad=dict(t=2, b=4),
        showactive=True, bgcolor="#f0efec", bordercolor=GRID, font=dict(size=11, color=INK_2),
        active=len(buttons) - 1,
        buttons=[dict(label=label, method="relayout", args=[{"xaxis.range": [start.isoformat(), end.isoformat()]}])
                 for label, start in buttons])])
    fig.update_xaxes(range=[(first - timedelta(days=3)).isoformat(), end.isoformat()],
                     rangeslider=dict(visible=True, thickness=0.08, bgcolor="#f3f2ee", bordercolor=GRID))
    # Header rows: title at the very top, legend under it, range buttons just above the plot.
    fig.update_layout(height=fig.layout.height + 72, margin=dict(t=112))
    _place_legend(fig)


def _day(x: date | datetime) -> date:
    return x.date() if isinstance(x, datetime) else x


def metric(fig: go.Figure, points: list[tuple], name: str, color: str, light: str, dark: str, unit: str,
           fmt: str, loess_days: float, hover_time: str = "%a %d %b %Y %H:%M") -> list[tuple]:
    """Raw readings as dots, plus their 7-day trailing mean as a spline. The average breaks wherever
    readings are more than 7 days apart (a 7-day average can't span months); a straight line in the
    lighter colour joins the two readings either side of each such gap. Returns the 7-day means."""
    from health.clean import WINDOW_DAYS, loess, trailing_mean

    means = trailing_mean(points)
    pts = sorted(points, key=lambda p: p[0])  # same order as `means`
    lx, ly, bx, by = [], [], [], []
    for i, (t, v) in enumerate(means):
        if i and (t - means[i - 1][0]).total_seconds() > WINDOW_DAYS * 86400:
            lx.append(None)
            ly.append(None)
            bx += [pts[i - 1][0], pts[i][0], None]
            by += [pts[i - 1][1], pts[i][1], None]
        lx.append(t)
        ly.append(v)
    # Each kind is its own legend group (one click toggles just it) and carries `meta` so the page's
    # checkboxes can toggle that kind across every chart.
    fig.add_scatter(x=[t for t, _ in points], y=[v for _, v in points], mode="markers", name=name,
                    legendgroup=f"{name} readings", meta="readings",
                    marker=dict(color=light, size=8, line=dict(color=SURFACE, width=2)),
                    hovertemplate=f"%{{x|{hover_time}}}<br><b>%{{y:{fmt}}} {unit}</b><extra>{name}</extra>")
    fig.add_scatter(x=bx, y=by, mode="lines", name=f"{name}, gap", legendgroup=f"{name} avg", meta="avg",
                    showlegend=False, line=dict(color=light, width=1.5, dash="dot"), hoverinfo="skip")
    fig.add_scatter(x=lx, y=ly, mode="lines", name=f"{name}, 7-day avg", legendgroup=f"{name} avg", meta="avg",
                    connectgaps=False, line=dict(color=color, width=2, dash="dash", shape="spline", smoothing=0.6),
                    hovertemplate=f"%{{x|%d %b %Y}}<br>7-day avg %{{y:{fmt}}} {unit}<extra></extra>")
    trend = loess(points, loess_days)
    fig.add_scatter(x=[t for t, _ in trend], y=[v for _, v in trend], mode="lines", connectgaps=False,
                    name=f"{name}, LOESS ±{loess_days:g}d", legendgroup=f"{name} loess", meta="loess",
                    line=dict(color=dark, width=3),
                    hovertemplate=f"%{{x|%d %b %Y}}<br>LOESS %{{y:{fmt}}} {unit}<extra></extra>")
    return means


def legend(fig: go.Figure) -> None:
    """Legend on its own row under the title (rows: title, legend, range buttons, plot)."""
    fig.update_layout(showlegend=True, legend=dict(orientation="h", x=0, xanchor="left", xref="container",
                                                   y=1, yanchor="top", yref="container", font=dict(color=INK_2),
                                                   bgcolor="rgba(0,0,0,0)", indentation=10))
    _place_legend(fig)


def _place_legend(fig: go.Figure) -> None:
    # Container-relative y must be recomputed whenever the height changes: 44px below the top.
    if fig.layout.showlegend and fig.layout.height:
        fig.update_layout(legend_y=1 - 44 / fig.layout.height)


def subtitle(fig: go.Figure, text: str) -> None:
    fig.update_layout(title_text=f"{fig.layout.title.text}<span style='font-size:12px;color:{INK_2}'>"
                                 f"&nbsp;&nbsp;{text}</span>")
