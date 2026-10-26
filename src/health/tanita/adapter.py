"""mytanita.eu CSV export -> body_comp rows.

Format verified against a real export (2026-10-14): comma-separated, quoted headers, dot
decimals, `Date` as local 'YYYY-MM-DD HH:MM:SS'; '-' or empty means no value.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

COLUMNS = {
    "weight_kg": "Weight (kg)",
    "body_fat_pct": "Body Fat (%)",
    "visceral_fat": "Visc Fat",
    "muscle_mass_kg": "Muscle Mass (kg)",
    "muscle_quality": "Muscle Quality",
    "body_water_pct": "Body Water (%)",
}
DATE_COLUMN = "Date"


def _num(s: str | None) -> float | None:
    s = (s or "").strip()
    return None if s in ("", "-") else float(s)


def rows(path: Path) -> list[tuple]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = {DATE_COLUMN, *COLUMNS.values()} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: Tanita export lacks columns {sorted(missing)}; got {reader.fieldnames}")
        by_ts = {}
        for r in reader:  # exports can repeat a measurement; last one wins
            ts = datetime.strptime(r[DATE_COLUMN].strip(), "%Y-%m-%d %H:%M:%S")
            by_ts[ts] = (ts, *(_num(r[c]) for c in COLUMNS.values()))
    return sorted(by_ts.values())
