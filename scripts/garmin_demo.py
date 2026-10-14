"""Load synthetic fixtures into a demo DB and render site/recovery.html."""
from pathlib import Path

from health import garmin_load
from health.charts import recovery
from health.db import ROOT, SITE_DIR, connect

FIX = ROOT / "tests" / "fixtures" / "garmin"
DB = ROOT / "data" / "garmin_demo.duckdb"

if __name__ == "__main__":
    DB.unlink(missing_ok=True)
    con = connect(DB)
    print(garmin_load.load(con, FIX))
    print(recovery.render(con, SITE_DIR / "recovery.html"))
