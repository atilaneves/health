import shutil
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from health import garmin_load, garmin_sync
from health.garmin import auth as garmin_auth
from health.charts import recovery

FIX = Path(__file__).parent / "fixtures" / "garmin"


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    garmin_load.load(c, FIX)
    return c


def test_loader_counts_and_values(con):
    n = lambda t: con.execute(f"select count(*) from {t}").fetchone()[0]
    assert n("garmin_daily") == 60
    assert n("garmin_sleep") == 58   # 2 days without sleep
    r = con.execute("select * from garmin_sleep where wake_date = '2026-08-14'").fetchone()
    assert r[1] > 20000 and r[6] is not None and r[9] < r[10]
    d = con.execute("select resting_hr, steps from garmin_daily where date='2026-08-14'").fetchone()
    assert 45 < d[0] < 60 and d[1] > 0


def test_loader_idempotent(con):
    before = con.execute("select * from garmin_sleep order by 1").fetchall()
    garmin_load.load(con, FIX)
    garmin_load.load(con, FIX)
    assert con.execute("select count(*) from garmin_sleep").fetchone()[0] == 58
    assert con.execute("select * from garmin_sleep order by 1").fetchall() == before


def test_loader_upsert_updates(tmp_path, con):
    raw = tmp_path / "garmin"
    shutil.copytree(FIX, raw)
    p = raw / "stats" / "2026-08-14.json"
    p.write_text(p.read_text().replace('"totalSteps"', '"totalSteps": 1234, "_x"'))
    garmin_load.load(con, raw)
    assert con.execute("select steps from garmin_daily where date='2026-08-14'").fetchone()[0] == 1234


def test_incremental_dates(tmp_path):
    today = date(2026, 10, 14)
    assert garmin_sync.start_date(None, today, tmp_path) == today - timedelta(days=30)
    (tmp_path / "stress").mkdir()
    (tmp_path / "stress" / "2026-10-10.json").write_text("{}")
    assert garmin_sync.start_date(None, today, tmp_path) == date(2026, 10, 7)
    assert garmin_sync.start_date(date(2026, 1, 1), today, tmp_path) == date(2026, 1, 1)


def test_sync_writes_files_and_backs_off(tmp_path):
    from garminconnect import GarminConnectTooManyRequestsError

    class Fake:
        calls = 0
        def get_stats(self, d):
            Fake.calls += 1
            if Fake.calls == 1:
                raise GarminConnectTooManyRequestsError("429")
            return {"totalSteps": 1}
        def __getattr__(self, name):
            return lambda d: None

    waits = []
    n = garmin_sync.sync(Fake(), date(2026, 1, 1), date(2026, 1, 2), raw=tmp_path,
                         delay=0, sleep=waits.append, backoff=(7,))
    assert n == 2 and 7 in waits
    assert (tmp_path / "stats" / "2026-01-02.json").exists()
    assert garmin_sync.last_stored_date(tmp_path) == date(2026, 1, 2)


def test_sync_stops_on_auth_error(tmp_path):
    from garminconnect import GarminConnectAuthenticationError

    class Fake:
        def __getattr__(self, name):
            def f(d):
                raise GarminConnectAuthenticationError("401")
            return f

    with pytest.raises(garmin_sync.StopSync):
        garmin_sync.sync(Fake(), date(2026, 1, 1), date(2026, 1, 2), raw=tmp_path, delay=0, sleep=lambda s: None)


def test_get_client_without_tokens(tmp_path, monkeypatch):
    monkeypatch.setattr(garmin_auth, "TOKEN_DIR", tmp_path / "nope")
    with pytest.raises(garmin_auth.GarminAuthError, match="garmin.auth login"):
        garmin_auth.get_client()
    assert garmin_auth.token_status()["present"] is False


def test_get_client_never_uses_password(tmp_path, monkeypatch):
    """Garbage token file: must raise GarminAuthError, not attempt a credential login."""
    monkeypatch.setattr(garmin_auth, "TOKEN_DIR", tmp_path)
    (tmp_path / "garmin_tokens.json").write_text("{}")
    with pytest.raises(garmin_auth.GarminAuthError):
        garmin_auth.get_client()


def test_rolling_mean_needs_five_days_and_skips_gaps():
    d0 = date(2026, 1, 1)
    vals = {d0 + timedelta(days=i): 50.0 + i for i in range(10)}
    del vals[d0 + timedelta(days=8)]
    m = recovery.rolling_mean(vals)
    assert m[d0 + timedelta(days=3)] is None                      # only 4 days so far
    assert m[d0 + timedelta(days=6)] == pytest.approx(53.0)       # mean of 50..56
    assert d0 + timedelta(days=8) not in m                        # gap not filled
    assert m[d0 + timedelta(days=9)] == pytest.approx((53 + 54 + 55 + 56 + 57 + 59) / 6)


def test_render(con, tmp_path):
    out = recovery.render(con, tmp_path / "r.html")
    assert "Resting heart rate" in out.read_text()
