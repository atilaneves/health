"""Load the cached raw data and render site/index.html. Never touches the network (see health.run)."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from plotly.io._utils import plotly_cdn_url

from health.charts import blood_pressure, body, sports, weight
from health.db import SITE_DIR, connect
from health.load import load

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Health</title>
<style>
body{{margin:0;background:#f9f9f7;color:#0b0b0b;font-family:system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:16px}}
h1{{font-size:22px;margin:8px 0 4px}} h2{{font-size:15px;color:#52514e;font-weight:600;margin:28px 0 8px}}
.meta{{color:#52514e;font-size:13px;margin-bottom:12px}}
.grid{{display:grid;gap:12px;margin:12px 0}}
.card{{background:#fcfcfb;border:1px solid #ebeae6;border-radius:8px;overflow:hidden;min-width:0}}
.card header{{display:flex;flex-wrap:wrap;align-items:baseline;column-gap:12px;row-gap:2px;padding:12px 16px 0}}
.card h3{{font-size:16px;font-weight:600;margin:0}}
.card header span{{font-size:12px;color:#52514e}}
/* Wide screens: two charts per row; an odd last chart takes the whole row. */
@media (min-width:1400px){{
  main{{max-width:2400px;padding:16px 24px}}
  .grid{{grid-template-columns:1fr 1fr}}
  .grid>.card:last-child:nth-child(odd){{grid-column:1/-1}}
}}
.toggles{{position:sticky;top:0;z-index:10;background:#f9f9f7;padding:8px 0;display:flex;gap:18px;
  flex-wrap:wrap;font-size:14px;border-bottom:1px solid #ebeae6}}
.toggles label{{display:flex;align-items:center;gap:6px;cursor:pointer}}
.tabs{{display:flex;gap:4px;margin:8px 0 0}}
.tabs button{{font:inherit;font-size:14px;color:#52514e;background:none;border:none;border-bottom:2px solid transparent;
  padding:6px 12px;cursor:pointer}}
.tabs button[aria-selected=true]{{color:#0b0b0b;font-weight:600;border-bottom-color:#2a78d6}}
[role=tabpanel][hidden]{{display:none}}
.toggles button{{margin-left:auto;font:inherit;font-size:13px;color:#52514e;background:#f0efec;
  border:1px solid #ebeae6;border-radius:6px;padding:2px 10px;cursor:pointer}}
</style></head><body><main>
<h1>Health</h1><div class="meta">{meta}</div>
<div class="tabs" role="tablist">
<button type="button" role="tab" data-tab="health" aria-selected="true">Health</button>
<button type="button" role="tab" data-tab="sports" aria-selected="false">Sports</button>
</div>
<section role="tabpanel" id="tab-health">
{health_toggles}
<h2>Garmin</h2><div class="grid">{garmin}</div>
<h2>Tanita</h2><div class="grid">{tanita}</div>
<h2>Blood pressure</h2><div class="grid">{blood_pressure}</div>
</section>
<section role="tabpanel" id="tab-sports" hidden>
{sports_toggles}
<div class="grid">{sports}</div>
</section>
</main>
<script src="{plotly_js}" charset="utf-8"></script>
<script>
// Each chart's figure sits in its card as JSON and is drawn only when its tab is first shown, once,
// with its y-axes already fitted: drawing every chart (and redrawing it to size and fit it) is slow.
const t = v => new Date(String(v).replace(" ", "T")).getTime();
const hidden = tr => tr.visible === false || tr.visible === "legendonly";
// The y-ranges ("yaxis", "yaxis2", ...) fitting the data inside x-range [x0, x1] (Plotly only fits x).
function yRanges(data, [x0, x1]) {{
  x0 = t(x0); x1 = t(x1);
  const span = {{}};
  for (const tr of data) {{
    if (!tr.x || !tr.y || hidden(tr)) continue;
    const s = span[tr.yaxis || "y"] ??= [Infinity, -Infinity];
    for (let i = 0; i < tr.x.length; i++) {{
      const y = tr.y[i], e = tr.error_y?.array?.[i] ?? 0;
      if (tr.x[i] == null || y == null) continue;
      const x = t(tr.x[i]);
      if (x >= x0 && x <= x1) {{ s[0] = Math.min(s[0], y - e); s[1] = Math.max(s[1], y + e); }}
    }}
  }}
  const out = {{}};
  for (const [axis, [lo, hi]] of Object.entries(span)) {{
    if (lo === Infinity) continue;
    const pad = Math.max((hi - lo) * 0.08, 0.5);
    out["yaxis" + axis.slice(1)] = [lo - pad, hi + pad];
  }}
  return out;
}}
function fitY(g) {{
  if (!g._fullLayout.xaxis.range) return;
  const update = {{}};
  for (const [axis, r] of Object.entries(yRanges(g.data, g._fullLayout.xaxis.range))) update[axis + ".range"] = r;
  if (!Object.keys(update).length) return;
  g._fitting = true;
  Plotly.relayout(g, update).then(() => g._fitting = false);
}}
const kinds = {{}};  // each tab's toggles: tab -> trace `meta` -> shown
const charts = [];   // drawn so far
const initial = new Map();  // chart -> the view it opened on, for Reset zoom
const tabOf = el => el.closest("[role=tabpanel]").id;
const config = {{displayModeBar: false, responsive: true, scrollZoom: true}};
function draw(card) {{
  const fig = JSON.parse(card.querySelector("script").textContent);
  const shown = kinds[tabOf(card)];
  for (const tr of fig.data) if (tr.meta in shown) tr.visible = shown[tr.meta] ? true : "legendonly";
  if (fig.layout.xaxis?.range)
    for (const [axis, r] of Object.entries(yRanges(fig.data, fig.layout.xaxis.range))) fig.layout[axis].range = r;
  const g = card.querySelector(".chart");
  Plotly.newPlot(g, fig.data, fig.layout, config);
  if (fig.layout.updatemenus) initial.set(g, {{range: [...fig.layout.xaxis.range], active: fig.layout.updatemenus[0].active}});
  g.on("plotly_relayout", ev => {{ if (!g._fitting && !Object.keys(ev).some(k => k.startsWith("yaxis") && k.endsWith("range"))) fitY(g); }});
  // Hiding a measure (legend click) refits the axes to what's left.
  g.on("plotly_restyle", () => {{ if (!g._fitting) fitY(g); }});
  charts.push(g);
}}
// Each tab has its own toggles and Reset zoom, acting on that tab's charts only.
for (const b of document.querySelectorAll(".reset")) b.addEventListener("click", () => {{
  for (const [g, v] of initial)
    if (tabOf(g) === tabOf(b)) Plotly.relayout(g, {{"xaxis.range": [...v.range], "updatemenus[0].active": v.active}});
}});
function setKind(tab, kind, on) {{
  kinds[tab][kind] = on;
  for (const g of charts.filter(g => tabOf(g) === tab)) {{
    const idx = g.data.map((tr, i) => tr.meta === kind ? i : -1).filter(i => i >= 0);
    if (idx.length) Plotly.restyle(g, {{visible: on ? true : "legendonly"}}, idx);
  }}
}}
for (const box of document.querySelectorAll(".toggles input")) {{
  const tab = tabOf(box), key = `health.show.${{tab}}.${{box.dataset.kind}}`;
  try {{ const v = localStorage.getItem(key); if (v !== null) box.checked = v === "1"; }} catch (e) {{}}
  (kinds[tab] ??= {{}})[box.dataset.kind] = box.checked;
  box.addEventListener("change", () => {{
    setKind(tab, box.dataset.kind, box.checked);
    try {{ localStorage.setItem(key, box.checked ? "1" : "0"); }} catch (e) {{}}
  }});
}}
// Tabs; the open one is remembered locally. A chart drawn earlier is resized only if the window changed
// size while its tab was hidden.
function showTab(name) {{
  for (const b of document.querySelectorAll("[role=tab]")) b.setAttribute("aria-selected", b.dataset.tab === name);
  for (const p of document.querySelectorAll("[role=tabpanel]")) p.hidden = p.id !== "tab-" + name;
  for (const card of document.querySelectorAll("#tab-" + name + " .card")) {{
    const g = card.querySelector(".chart");
    if (!g.data) draw(card);
    else if (g._fullLayout.width !== g.clientWidth) Plotly.Plots.resize(g);
  }}
}}
for (const b of document.querySelectorAll("[role=tab]")) b.addEventListener("click", () => {{
  showTab(b.dataset.tab);
  try {{ localStorage.setItem("health.tab", b.dataset.tab); }} catch (e) {{}}
}});
let tab = "health";
try {{ const v = localStorage.getItem("health.tab"); if (v && document.getElementById("tab-" + v)) tab = v; }} catch (e) {{}}
showTab(tab);
</script>
</body></html>"""


# (trace `meta`, label, on at first): the kinds of line a tab's checkboxes toggle.
KINDS = [("readings", "Readings", True), ("avg", "Average", True), ("trend", "Trend", True),
         ("line", "Line between readings", False)]


def _toggles(kinds: list[str]) -> str:
    """A tab's own checkboxes (one per kind of line its charts have) and Reset zoom button."""
    boxes = "".join(f'<label><input type="checkbox" data-kind="{k}"{" checked" if on else ""}> {label}</label>'
                    for k, label, on in KINDS if k in kinds)
    return f'<div class="toggles">{boxes}<button type="button" class="reset">Reset zoom</button></div>'


def _card(fig) -> str:
    """The figure as JSON, drawn by the page script (see PAGE) when its tab is first shown."""
    data = fig.to_json().replace("</", "<\\/")  # can't close the script tag early
    head = f'<h3>{html.escape(fig.layout.meta["title"])}</h3>'
    if fig.layout.meta["subtitle"]:
        head += f'<span>{html.escape(fig.layout.meta["subtitle"])}</span>'
    return (f'<div class="card"><header>{head}</header><div class="chart"></div>'
            f'<script type="application/json">{data}</script></div>')



def render(con=None) -> Path:
    con = con or connect()
    counts = load(con)
    tanita_figs = body.figures(con)
    meta = html.escape(f"Built {datetime.now():%Y-%m-%d %H:%M} · "
                       + " · ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items()))
    page = PAGE.format(meta=meta, plotly_js=plotly_cdn_url(),
                       garmin=_card(weight.figure(con)),
                       tanita="".join(_card(f) for f in tanita_figs),
                       blood_pressure=_card(blood_pressure.figure(con)),
                       sports="".join(_card(f) for f in sports.figures(con)),
                       health_toggles=_toggles(["readings", "avg", "trend", "line"]),
                       sports_toggles=_toggles(["readings", "trend", "line"]))
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    out = SITE_DIR / "index.html"
    out.write_text(page)
    return out


if __name__ == "__main__":
    print(render())
