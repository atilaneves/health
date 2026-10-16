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
  body_fat_pct DOUBLE,
  visceral_fat DOUBLE,      -- Tanita's visceral fat rating, unitless
  muscle_mass_kg DOUBLE,
  muscle_quality DOUBLE
);
"""

WEIGH_INS = ("date", "ts", "weight_kg")
BLOOD_PRESSURE = ("ts", "systolic", "diastolic", "pulse")
BODY_COMP = ("ts", "body_fat_pct", "visceral_fat", "muscle_mass_kg", "muscle_quality")
