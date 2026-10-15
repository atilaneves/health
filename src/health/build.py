"""Load the cached raw data and render site/index.html. Never touches the network (see health.run)."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from health.charts import blood_pressure, body, weight
from health.db import SITE_DIR, connect
from health.load import load

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Health</title>
<style>
body{{margin:0;background:#f9f9f7;color:#0b0b0b;font-family:system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:16px}}
h1{{font-size:22px;margin:8px 0 4px}} h2{{font-size:15px;color:#52514e;font-weight:600;margin:28px 0 8px}}
.meta{{color:#52514e;font-size:13px;margin-bottom:12px}}
.card{{background:#fcfcfb;border:1px solid #ebeae6;border-radius:8px;margin:12px 0;overflow:hidden}}
.toggles{{position:sticky;top:0;z-index:10;background:#f9f9f7;padding:8px 0;display:flex;gap:18px;
  flex-wrap:wrap;font-size:14px;border-bottom:1px solid #ebeae6}}
.toggles label{{display:flex;align-items:center;gap:6px;cursor:pointer}}
</style></head><body><main>
<h1>Health</h1><div class="meta">{meta}</div>
<div class="toggles">
<label><input type="checkbox" data-kind="readings" checked> Readings</label>
<label><input type="checkbox" data-kind="avg" checked> 7-day average</label>
<label><input type="checkbox" data-kind="trend" checked> Trend</label>
</div>
<h2>Garmin</h2>{garmin}
<h2>Tanita</h2>{tanita}
<h2>Blood pressure</h2>{blood_pressure}
</main>
<script>
// Fit each chart's y-axis to the data inside the visible x-range (Plotly only does x).
const t = v => new Date(String(v).replace(" ", "T")).getTime();
function fitY(g) {{
  const [x0, x1] = g._fullLayout.xaxis.range.map(t);
  let lo = Infinity, hi = -Infinity;
  for (const tr of g._fullData) {{
    if (!tr.x || !tr.y || tr.yaxis !== "y") continue;
    for (let i = 0; i < tr.x.length; i++) {{
      const y = tr.y[i];
      if (tr.x[i] == null || y == null) continue;
      const x = t(tr.x[i]);
      if (x >= x0 && x <= x1) {{ lo = Math.min(lo, y); hi = Math.max(hi, y); }}
    }}
  }}
  if (lo === Infinity) return;
  const pad = Math.max((hi - lo) * 0.08, 0.5);
  g._fitting = true;
  Plotly.relayout(g, {{"yaxis.range": [lo - pad, hi + pad]}}).then(() => g._fitting = false);
}}
const charts = [...document.querySelectorAll(".js-plotly-plot")];
for (const g of charts) {{
  g.on("plotly_relayout", ev => {{ if (!g._fitting && !("yaxis.range" in ev)) fitY(g); }});
  fitY(g);
}}
// Page-wide toggles: show/hide one kind of line (by trace `meta`) on every chart; remembered locally.
function setKind(kind, on) {{
  for (const g of charts) {{
    const idx = g.data.map((tr, i) => tr.meta === kind ? i : -1).filter(i => i >= 0);
    if (idx.length) Plotly.restyle(g, {{visible: on ? true : "legendonly"}}, idx);
  }}
}}
for (const box of document.querySelectorAll(".toggles input")) {{
  const key = "health.show." + box.dataset.kind;
  try {{ const v = localStorage.getItem(key); if (v !== null) box.checked = v === "1"; }} catch (e) {{}}
  if (!box.checked) setKind(box.dataset.kind, false);
  box.addEventListener("change", () => {{
    setKind(box.dataset.kind, box.checked);
    try {{ localStorage.setItem(key, box.checked ? "1" : "0"); }} catch (e) {{}}
  }});
}}
</script>
</body></html>"""


def _card(fig, first: bool) -> str:
    return '<div class="card">' + fig.to_html(full_html=False, include_plotlyjs="cdn" if first else False,
                                               config={"displayModeBar": False, "responsive": True, "scrollZoom": True}) + "</div>"


def render(con=None) -> Path:
    con = con or connect()
    counts = load(con)
    tanita_figs = body.figures(con)
    meta = html.escape(f"Built {datetime.now():%Y-%m-%d %H:%M} · "
                       + " · ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items()))
    page = PAGE.format(meta=meta,
                       garmin=_card(weight.figure(con), True),
                       tanita="".join(_card(f, False) for f in tanita_figs),
                       blood_pressure=_card(blood_pressure.figure(con), False))
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    out = SITE_DIR / "index.html"
    out.write_text(page)
    return out


if __name__ == "__main__":
    print(render())
