"""Do the obvious thing: fetch whatever wasn't fetched today, log in only when a source needs it,
rebuild the page and open it. Invoked by ./run.sh.

    ./run.sh               # normal use
    ./run.sh --refresh     # ignore today's cache
    ./run.sh --offline     # never touch the network
    ./run.sh --no-open     # don't open the browser
"""

from __future__ import annotations

import argparse
import webbrowser
from collections.abc import Callable

from health import build
from health.garmin import auth as garmin_auth
from health.garmin import fetch as garmin_fetch
from health.tanita import auth as tanita_auth
from health.tanita import fetch as tanita_fetch


def _sync(name: str, fetch: Callable[[], None], login: Callable[[], None], auth_error: type[Exception]) -> None:
    """Fetch; on an auth error log in interactively and try once more. Other failures leave the
    cache as it is, so the page still builds from what's already on disk."""
    try:
        try:
            fetch()
        except auth_error as e:
            print(f"{name}: {e}\n{name}: logging in")
            login()
            fetch()
        print(f"{name}: up to date")
    except Exception as e:  # noqa: BLE001 - report and carry on with cached data
        print(f"{name}: not updated ({type(e).__name__}: {e}); using cached data")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="run.sh", description=__doc__.split("\n\n")[0])
    p.add_argument("--refresh", action="store_true", help="ignore today's cache")
    p.add_argument("--offline", action="store_true", help="never touch the network")
    p.add_argument("--no-open", action="store_true", help="don't open the page in the browser")
    a = p.parse_args(argv)

    if not a.offline:
        def garmin():
            client = garmin_fetch.LazyClient()
            for kind in garmin_fetch.KINDS:
                garmin_fetch.fetch(kind, refresh=a.refresh, client=client)

        _sync("Garmin", garmin, garmin_auth.login_interactive, garmin_auth.GarminAuthError)
        _sync("Tanita", lambda: tanita_fetch.fetch(refresh=a.refresh), tanita_auth.login_interactive,
              tanita_auth.TanitaAuthError)

    page = build.render()
    print(f"page: {page}")
    if not a.no_open:
        webbrowser.open(page.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
