"""Incremental Garmin Connect fetch -> raw/garmin/<kind>/<YYYY-MM-DD>.json.

    uv run python -m health.garmin_sync [--since YYYY-MM-DD] [--until YYYY-MM-DD]

Dates are Garmin "calendarDate"s (for sleep: the wake-up date).
Each kind is one garminconnect call per day (method names verified in 0.3.17).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from health.db import RAW_DIR

GARMIN_RAW = RAW_DIR / "garmin"
OVERLAP_DAYS = 3
DEFAULT_LOOKBACK_DAYS = 30
REQUEST_DELAY_S = 1.5
BACKOFF_S = (30, 90, 240)  # waits after successive 429s on the same request

# kind -> (client, 'YYYY-MM-DD') -> JSON
KINDS: dict[str, Callable] = {
    "stats": lambda c, d: c.get_stats(d),  # steps, RHR, stress, body battery, intensity min
    "sleep": lambda c, d: c.get_sleep_data(d),
    "rhr": lambda c, d: c.get_rhr_day(d),
    "body_battery": lambda c, d: c.get_body_battery(d),
    "stress": lambda c, d: c.get_stress_data(d),
}
# Last kind written last, so "latest stored date" is only advanced by complete days.
MARKER_KIND = "stress"


class StopSync(Exception):
    """Fatal condition (auth / persistent rate limit); stop cleanly."""


def last_stored_date(raw: Path = GARMIN_RAW) -> date | None:
    d = raw / MARKER_KIND
    days = sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []
    return date.fromisoformat(days[-1]) if days else None


def start_date(since: date | None, today: date, raw: Path = GARMIN_RAW) -> date:
    if since:
        return since
    last = last_stored_date(raw)
    if last is None:
        return today - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    return last - timedelta(days=OVERLAP_DAYS)


def _save(raw: Path, kind: str, day: str, payload) -> None:
    d = raw / kind
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".{day}.tmp"
    tmp.write_text(json.dumps(payload, indent=1))
    tmp.replace(d / f"{day}.json")


def _call(fn, *, sleep, backoff=BACKOFF_S):
    from garminconnect import (
        GarminConnectAuthenticationError,
        GarminConnectTooManyRequestsError,
    )

    for wait in (*backoff, None):
        try:
            return fn()
        except GarminConnectAuthenticationError as e:
            raise StopSync(f"auth error: {e}. Re-run `python -m health.garmin.auth login`.") from e
        except GarminConnectTooManyRequestsError as e:
            if wait is None:
                raise StopSync("persistent HTTP 429; try again later") from e
            print(f"  429, backing off {wait}s", file=sys.stderr)
            sleep(wait)


def sync(client, start: date, end: date, raw: Path = GARMIN_RAW,
         delay: float = REQUEST_DELAY_S, sleep=time.sleep, backoff=BACKOFF_S) -> int:
    """Fetch [start, end] day by day. Returns number of days completed."""
    from garminconnect import GarminConnectConnectionError

    done, day = 0, start
    while day <= end:
        ds = day.isoformat()
        for kind, getter in KINDS.items():
            try:
                payload = _call(lambda: getter(client, ds), sleep=sleep, backoff=backoff)
            except StopSync:
                raise
            except GarminConnectConnectionError as e:  # e.g. 404: nothing for that day
                print(f"  {ds} {kind}: {e}", file=sys.stderr)
                payload = None
            _save(raw, kind, ds, payload)
            sleep(delay)
        done += 1
        print(f"{ds} ok")
        day += timedelta(days=1)
    return done


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--since", type=date.fromisoformat)
    p.add_argument("--until", type=date.fromisoformat)
    args = p.parse_args(argv)

    from health.garmin.auth import GarminAuthError, get_client

    today = date.today()
    start, end = start_date(args.since, today), args.until or today
    try:
        client = get_client()
        print(f"Syncing {start} .. {end}")
        n = sync(client, start, end)
    except (GarminAuthError, StopSync) as e:
        print(f"Stopped: {e}", file=sys.stderr)
        return 2
    print(f"Done: {n} days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
