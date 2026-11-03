"""The project's own tables. Adapters turn vendor data into these rows; cleaning and charts only
ever read these tables, never vendor formats. All timestamps are local wall-clock time."""

SCHEMA = """
CREATE OR REPLACE TABLE weigh_ins (
  date DATE NOT NULL,
  ts TIMESTAMP,              -- NULL when the source only recorded a date
  weight_kg DOUBLE NOT NULL
);
CREATE OR REPLACE TABLE blood_pressure (
  ts TIMESTAMP NOT NULL,
  systolic INTEGER NOT NULL,
  diastolic INTEGER NOT NULL,
  pulse INTEGER
);
CREATE OR REPLACE TABLE body_comp (
  ts TIMESTAMP PRIMARY KEY,
  weight_kg DOUBLE,         -- Tanita's own weighing, not Garmin's
  body_fat_pct DOUBLE,
  visceral_fat DOUBLE,      -- Tanita's visceral fat rating, unitless
  muscle_mass_kg DOUBLE,
  muscle_quality DOUBLE,
  body_water_pct DOUBLE
);
CREATE OR REPLACE TABLE activities (
  ts TIMESTAMP NOT NULL,    -- start
  type VARCHAR NOT NULL,    -- Garmin's activity type key, e.g. 'running'
  name VARCHAR,
  distance_km DOUBLE,
  avg_speed_kmh DOUBLE,
  calories DOUBLE,          -- kcal
  avg_hr DOUBLE,
  max_hr DOUBLE,
  lat DOUBLE,               -- where it started
  lon DOUBLE,
  vo2max DOUBLE             -- Garmin's VO2max estimate after it, ml/kg/min (runs only)
);
CREATE OR REPLACE TABLE dexa (
  date DATE PRIMARY KEY,
  total_kg DOUBLE,
  fat_kg DOUBLE,
  lean_kg DOUBLE,           -- lean soft tissue, bone excluded (total = fat + lean + bone)
  fat_pct DOUBLE,
  visceral_fat_kg DOUBLE    -- VAT mass (GE CoreScan); see charts.body for the rating conversion
);
"""

WEIGH_INS = ("date", "ts", "weight_kg")
BLOOD_PRESSURE = ("ts", "systolic", "diastolic", "pulse")
BODY_COMP = ("ts", "weight_kg", "body_fat_pct", "visceral_fat", "muscle_mass_kg", "muscle_quality",
             "body_water_pct")
ACTIVITIES = ("ts", "type", "name", "distance_km", "avg_speed_kmh", "calories", "avg_hr", "max_hr", "lat", "lon",
              "vo2max")
DEXA = ("date", "total_kg", "fat_kg", "lean_kg", "fat_pct", "visceral_fat_kg")
