# health

Custom graphs of my Garmin and Tanita data, because the apps' own graphs aren't good enough.

- **Garmin:** weight and blood pressure.
- **Tanita:** body fat %, muscle mass and muscle quality.

## Use

```
./run.sh               # fetch what wasn't fetched today, log in if needed, rebuild, open the page
./run.sh --no-open     # same, without opening a browser tab
./run.sh --offline     # rebuild from the cache only
./run.sh --refresh     # ignore today's cache
```

The output is `site/index.html`.

## How it works

```
Garmin Connect ─┐                    ┌─ weigh_ins ──────┐
                ├─ raw/ (cache) ─ adapters ─┼─ blood_pressure ─┼─ charts ─ site/index.html
mytanita.eu ────┘                    └─ body_comp ──────┘
```

- **Fetch:** `health.garmin.fetch` and `health.tanita.fetch` store responses verbatim under `raw/`.
  - A fetch made today is reused without touching the network.
  - Garmin only re-fetches uncovered days, plus the last 3 days of older fetches.
- **Adapters:** `garmin/weight.py`, `garmin/blood_pressure.py` and `tanita/adapter.py` are the only code that knows vendor formats. Each was written against real responses.
- **Tables:** `schema.py` defines the tables, with local wall-clock timestamps. `load.py` rebuilds them from `raw/` on every run.
- **Charts:** `charts/` reads only those tables. Each metric shows:
  - the readings;
  - a 7-day trailing average, broken across gaps of more than 7 days, with a lighter line joining the readings either side of a gap;
  - a LOESS trend: a tricube-weighted local mean over ±30 days (±14 for Tanita), drawn only between readings.

  The page has range buttons, x-zoom with an auto-fitted y-axis, and page-wide toggles.

## Logins

- **Garmin:** `python -m health.garmin.auth login` logs in once, with MFA.
  - Only the OAuth tokens are kept, in `~/.local/share/health/garmin_tokens/`, and they refresh themselves.
  - Avoid repeated fresh logins, because Garmin answers them with HTTP 429.
- **Tanita:** there's no API. The code scrapes the mytanita.eu login form and its CSV export.
  - The password is kept in the system keyring and the session cookies in `~/.local/share/health/tanita/`.
  - It logs in again only when the saved session is rejected.

`run.sh` starts either login by itself when it's needed.

## Never committed

`raw/`, `data/` and `site/` hold personal health data and are gitignored.
