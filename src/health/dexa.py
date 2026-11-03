"""DEXA scans, typed in by hand from the reports into raw/dexa/scans.csv (the PDFs are images, and there
are only a few scans). Lines starting with # are comments."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from health.db import RAW_DIR

SCANS = RAW_DIR / "dexa" / "scans.csv"


def rows(path: Path = SCANS) -> list[tuple]:
    """(date, total_kg, fat_kg, lean_kg, fat_pct, visceral_fat_kg) per scan; none if there's no file."""
    if not path.exists():
        return []
    with path.open() as f:
        lines = [line for line in f if line.strip() and not line.startswith("#")]
    return [(date.fromisoformat(r["date"]), *(float(r[k]) if r[k] else None for k in
             ("total_kg", "fat_kg", "lean_kg", "fat_pct", "visceral_fat_kg")))
            for r in csv.DictReader(lines)]
