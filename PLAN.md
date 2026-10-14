# Custom health graphs: Tanita + Garmin

Research date: 2026-10-14. This plan combines the findings of four research agents. Items marked **(unverified)** still need checking against real data.

## Architecture

```
Garmin Connect ──garminconnect──┐
Garmin bulk export zip ─────────┼──► raw/ (JSON, FIT, CSV; never edited) ──► load.py ──► data/health.duckdb ──► charts/ ──► build.py ──► site/*.html
Tanita CSV (emailed export) ────┘                                                     └──► notebooks/explore.py (marimo)
```

- **The raw files are the source of truth.** The DuckDB file is derived from them and can be rebuilt at any time, so schema mistakes are cheap.
- **DuckDB** suits this data size: daily rows plus per-second activity samples over years. It has good window functions (EWMA, rolling bands) and works well with Polars and Pandas.
- **Plotly charts rendered to static HTML** after each sync. Nothing to keep running, works on a phone, and keeps full control over every chart.
- **marimo** is for exploring the data. A chart that proves useful moves into `charts/`.
- **A systemd user timer** runs the sync.

## Data sources

### Garmin
- **Ongoing sync:** `garminconnect` >= 0.3.17 (cyberjunky). Garmin changed its login in March 2026, which broke `garth` and the libraries built on it. `garminconnect` now logs in the way the phone app does.
  - Log in once interactively (with MFA) and save the token in `~/.garminconnect`, readable only by you. After that, reuse the saved token and never log in again from scripts. Repeated logins get blocked with HTTP 429.
  - Each run fetches the days since the last stored date, plus a 3-day overlap, because Garmin back-fills sleep and HRV.
  - Upsert by primary key. Pin the library version and expect to bump it when Garmin changes things again.
  - Metrics: daily stats, sleep (with stages), HRV, resting HR, stress, Body Battery, training readiness and status, VO2max, and activities. For each activity, also download the original FIT file.
- **History and fallback:** the GDPR bulk export (Account → Data Management → Export Your Data). Parse it into the same raw tables. **(unverified: the file layout, and HRV possibly sits in obscure FIT files)**
- **FIT parsing:** `garmin-fit-sdk`, which is official and current. Not `fitparse`, which is stale.
- **Alternative if writing the sync is unappealing:** GarminDB 4.0.0. **(unverified: whether its login works after the auth change)**

### Tanita
- **Primary:** the CSV export the app emails you (My Measurements → Export CSV via email). It has the richest data. **(unverified: confirmed only for the MyTANITA Healthcare app, not yet for the consumer My Tanita app; column names unknown until we have a sample)**
- It's manual. Export monthly, or automate it later by fetching the email over IMAP.
- **Avoid:** syncing through Garmin, Apple Health or Health Connect. These keep only weight, BMI and fat % and drop the rest. Bluetooth has no open-source support for Tanita scales. The Health Planet API is probably Japan-only.

## Schema (first pass)

| table | key | notes |
|---|---|---|
| `garmin_daily` | date | steps, RHR, stress, body battery, intensity minutes |
| `garmin_sleep` | wake_date | duration, stages, score, bed/wake times (sleep is assigned to the date you wake up) |
| `garmin_hrv` | wake_date | overnight avg, Garmin's baseline |
| `garmin_training` | date | training load, readiness, VO2max |
| `activities` | activity_id | summary, FIT path |
| `activity_samples` | activity_id, ts | per-second HR, pace, power |
| `body_comp` | ts | weight, fat %, muscle, visceral fat, water, BMR, metabolic age, segmental fields |
| `annotations` | date | manual tags: alcohol, illness, travel/timezone |

Store timestamps in UTC with the UTC offset, and work out the local date once.

## Charts (in priority order)

1. **Weight trend:** raw weigh-ins as dots plus an exponentially smoothed line (the Hacker's Diet method, about a 10–20 day span). The slope gives the implied daily calorie surplus or deficit.
2. **Fat mass and lean mass in kg**, using weekly medians. Shows whether a falling fat % is really fat loss.
3. **HRV vs. your own normal range:** each night's value, a 7-day mean, and a band of the previous 60 days' mean ± 1 SD.
4. **Resting HR and HRV on one chart, with resting HR inverted.** Illness or overreaching shows when both move the wrong way together.
5. **Fitness, fatigue and form:** 42-day and 7-day averages of daily training load, and form as their difference, with daily load as bars underneath.
6. **Calendar heatmaps** of sleep, HRV, steps and Body Battery, one colour scale per metric.
7. **Day-of-week patterns** (median and range) for sleep, HRV, stress, and weight measured against its trend line.
8. **Sleep timing:** bedtime and wake time as a band, with duration as bars. Treat the stage breakdown as indicative only, because wrist sleep tracking is weak.
9. **Event study:** next-night HRV and resting HR change after tagged days (alcohol, late training), 0–3 days later. Test only a few hypotheses chosen in advance, so chance correlations don't look like findings.
10. **VO2max with 28-day smoothing** next to the fitness line and weekly volume.
11. *Secondary:* 7-day HRV variability, and the acute:chronic training-load ratio. Show the ratio carefully, as its scientific basis is contested.

## Data hygiene
- **Tanita:** keep only morning readings (05:00–10:00), one per day (the first, or the median if several). Flag outliers using a rolling median ± 3 MAD or a jump of more than 2 kg. Grey them out rather than deleting them.
- **Gaps:** compute on a calendar-day index. Don't forward-fill silently. Rolling statistics require a minimum count (≥5 of 7 days, ≥40 of 60). Tell "watch not worn" apart from a genuine zero.
- **Lagged analysis:** line up the evening of day D with the sleep that ends on D+1.

## Project layout
```
health/
  pyproject.toml            # uv; garminconnect, garmin-fit-sdk, duckdb, polars, plotly, marimo
  src/health/
    sync_garmin.py          # incremental API fetch -> raw/garmin/
    import_garmin_export.py # bulk-export zip -> raw/garmin/
    import_tanita.py        # CSV -> raw/tanita/
    load.py                 # raw/ -> DuckDB (idempotent)
    charts/                 # one module per chart: (con) -> plotly Figure
  build.py                  # renders site/index.html + per-chart pages
  notebooks/explore.py      # marimo
  raw/  data/  site/        # gitignored
  systemd/health-sync.{service,timer}
```

## Milestones
1. **Bootstrap:** create the project skeleton, then the Tanita CSV importer, `body_comp`, and charts 1–2. This gives a quick result with the simplest data source.
2. **Garmin sync:** token login and an incremental fetch of daily stats, sleep and HRV, then charts 3, 4, 6, 7 and 8.
3. **Activities:** FIT download and parsing, training load, then charts 5 and 10.
4. **Backfill:** import the bulk export to load the history.
5. **Automation:** systemd timer, a notification when a sync fails, and the static site published to the phone (Tailscale or Syncthing).
6. **Analysis:** an annotations input, then chart 9.

## Open inputs needed
- The Tanita model number, the app you use, and your account region, plus one sample CSV export.
- A request for the Garmin bulk export now, since it takes a day or two.
- The Garmin watch model, which affects whether HRV and training readiness are available.
- Phone access: a Tailscale-served site, or HTML synced with Syncthing?
