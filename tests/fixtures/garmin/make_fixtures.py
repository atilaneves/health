"""Generate synthetic raw Garmin JSON (shapes: see garmin_load.parse_*). Deterministic.

    python make_fixtures.py   # writes <kind>/<date>.json next to this file
Shape confidence: sleep/stats/rhr moderate-high (long-standing Garmin shapes, from memory
of real responses); body_battery/stress moderate; none verified against a live account.
"""
import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
START, DAYS = date(2026, 8, 14), 60
MISSING_SLEEP = {9, 21}
ILL = range(50, 54)               # illness: RHR up


def ms(dt):  # naive-as-UTC datetime -> epoch ms
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def write(kind, day, payload):
    p = HERE / kind
    p.mkdir(exist_ok=True)
    (p / f"{day}.json").write_text(json.dumps(payload, indent=1))


def main():
    rnd = random.Random(42)
    for i in range(DAYS):
        d = START + timedelta(days=i)
        ds = d.isoformat()
        ill = i in ILL
        rhr = 52 + rnd.gauss(0, 1.2) + (6 if ill else 0)
        # sleep: wake date d, bed the evening before
        bed = datetime(d.year, d.month, d.day) - timedelta(hours=1.0 - rnd.gauss(0, 0.6))
        dur = int((7.3 + rnd.gauss(0, 0.6)) * 3600)
        wake = bed + timedelta(seconds=dur + 1800)
        deep, rem = int(dur * 0.17), int(dur * 0.22)
        offset = timedelta(hours=1)  # local = UTC+1
        if i not in MISSING_SLEEP:
            write("sleep", ds, {"dailySleepDTO": {
                "calendarDate": ds, "sleepTimeSeconds": dur,
                "sleepStartTimestampGMT": ms(bed - offset), "sleepEndTimestampGMT": ms(wake - offset),
                "sleepStartTimestampLocal": ms(bed), "sleepEndTimestampLocal": ms(wake),
                "deepSleepSeconds": deep, "remSleepSeconds": rem,
                "lightSleepSeconds": dur - deep - rem - 600, "awakeSleepSeconds": 1800,
                "sleepScores": {"overall": {"value": int(min(95, max(40, 78 + rnd.gauss(0, 7) - (10 if ill else 0)))),
                                            "qualifierKey": "GOOD"}},
            }, "restingHeartRate": round(rhr)})
        else:
            write("sleep", ds, {"dailySleepDTO": {"calendarDate": ds, "sleepTimeSeconds": None}})
        steps = int(max(1500, rnd.gauss(8500, 3000)))
        stress = int(max(15, rnd.gauss(30, 6) + (10 if ill else 0)))
        write("stats", ds, {
            "calendarDate": ds, "totalSteps": steps, "totalDistanceMeters": steps * 0.78,
            "restingHeartRate": round(rhr), "minHeartRate": round(rhr) - 4, "maxHeartRate": 150,
            "averageStressLevel": stress, "maxStressLevel": 90,
            "bodyBatteryHighestValue": 90 - (30 if ill else 0), "bodyBatteryLowestValue": 15,
            "bodyBatteryChargedValue": 70, "bodyBatteryDrainedValue": 65,
            "moderateIntensityMinutes": int(abs(rnd.gauss(15, 15))), "vigorousIntensityMinutes": int(abs(rnd.gauss(8, 10))),
            "totalKilocalories": 2400, "activeKilocalories": 500, "floorsAscended": 9.0})
        write("rhr", ds, {"userProfilePK": 1, "statisticsStartDate": ds, "statisticsEndDate": ds,
                          "allMetrics": {"metricsMap": {"WELLNESS_RESTING_HEART_RATE": [
                              {"value": float(round(rhr)), "calendarDate": ds}]}}})
        write("body_battery", ds, [{"date": ds, "charged": 70, "drained": 65, "startTimestampGMT": f"{ds}T00:00:00.0",
                                    "bodyBatteryValuesArray": [[ms(datetime(d.year, d.month, d.day)), 60]]}])
        write("stress", ds, {"calendarDate": ds, "overallStressLevel": stress, "avgStressLevel": stress,
                             "maxStressLevel": 90, "stressValuesArray": []})


if __name__ == "__main__":
    main()
