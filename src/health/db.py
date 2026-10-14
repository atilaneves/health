"""Shared DuckDB connection helper."""

from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "health.duckdb"
RAW_DIR = ROOT / "raw"
SITE_DIR = ROOT / "site"


def connect(path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))
