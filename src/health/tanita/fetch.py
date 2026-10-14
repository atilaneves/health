"""Download the full mytanita.eu CSV export, cached in raw/tanita/.

    uv run python -m health.tanita.fetch [--refresh]

The export is the whole history in one request. A download from today is reused without touching
the network; an unchanged download only refreshes the cached file's timestamp.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import requests

from health.db import RAW_DIR
from health.tanita import auth

EXPORT_PATH = "/en/user/export-csv"
TANITA_RAW = RAW_DIR / "tanita"


class TanitaFetchError(RuntimeError):
    pass


def latest_export(raw: Path = TANITA_RAW) -> Path | None:
    files = sorted(raw.glob("export_*.csv")) if raw.is_dir() else []
    return files[-1] if files else None


def _is_csv(resp: requests.Response) -> bool:
    head = resp.content[:512].lstrip().lower()
    return resp.ok and not head.startswith((b"<!doctype", b"<html")) and not auth.is_login_page(resp)


def _download(session: requests.Session) -> requests.Response:
    return session.get(auth.BASE + EXPORT_PATH, timeout=auth.TIMEOUT_S)


def fetch(refresh: bool = False, raw: Path = TANITA_RAW,
          now: Callable[[], datetime] = datetime.now) -> tuple[Path, bool]:
    """Return (path to the newest export, whether the network was used)."""
    latest = latest_export(raw)
    if latest and not refresh and datetime.fromtimestamp(latest.stat().st_mtime).date() == now().date():
        return latest, False
    session = auth.get_session()
    r = _download(session)
    if not _is_csv(r):  # saved session expired: log in again once
        auth.relogin(session)
        r = _download(session)
    if not _is_csv(r):
        raise TanitaFetchError(f"export did not return a CSV (HTTP {r.status_code}, "
                               f"{r.headers.get('content-type', '?')}); the site may have changed")
    auth.save_session(session, auth._saved()["email"])  # keep any refreshed cookies
    if latest and latest.read_bytes() == r.content:
        os.utime(latest)
        return latest, True
    raw.mkdir(parents=True, exist_ok=True)
    p = raw / f"export_{now():%Y%m%dT%H%M%S}.csv"
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(r.content)
    os.replace(tmp, p)
    return p, True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="health.tanita.fetch")
    p.add_argument("--refresh", action="store_true", help="download even if the cached export is recent")
    a = p.parse_args(argv)
    try:
        path, network = fetch(refresh=a.refresh)
    except (auth.TanitaAuthError, TanitaFetchError) as e:
        print(e)
        return 2
    print(f"{'downloaded' if network else 'cached (no network)'}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
