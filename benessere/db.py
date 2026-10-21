"""Storage SQLite local-first.

Il DB vive in data/benessere.db (override con env BENESSERE_DB).
Tutte le tabelle sono append-friendly: il sync deduplica su chiavi naturali.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "benessere.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hr_samples (
  ts TEXT PRIMARY KEY,
  bpm INTEGER NOT NULL,
  source TEXT NOT NULL DEFAULT 'zepp'
);

CREATE TABLE IF NOT EXISTS hrv_daily (
  night_date TEXT PRIMARY KEY,
  rmssd_ms REAL,
  sdnn_ms REAL,
  source TEXT NOT NULL DEFAULT 'zepp'
);

CREATE TABLE IF NOT EXISTS temp_daily (
  night_date TEXT PRIMARY KEY,
  deviation REAL,
  source TEXT NOT NULL DEFAULT 'zepp'
);

CREATE TABLE IF NOT EXISTS spo2_samples (
  ts TEXT PRIMARY KEY,
  pct REAL NOT NULL,
  source TEXT NOT NULL DEFAULT 'zepp'
);

CREATE TABLE IF NOT EXISTS sleeps (
  night_date TEXT PRIMARY KEY,
  start TEXT, stop TEXT,
  deep_min INTEGER, light_min INTEGER, rem_min INTEGER, awake_min INTEGER,
  score REAL,
  source TEXT NOT NULL DEFAULT 'zepp'
);

CREATE TABLE IF NOT EXISTS days (
  date TEXT PRIMARY KEY,
  steps INTEGER, distance_m REAL,
  active_kcal REAL, total_kcal REAL,
  resting_hr INTEGER,
  weight_kg REAL,
  source TEXT NOT NULL DEFAULT 'zepp'
);

CREATE TABLE IF NOT EXISTS workouts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  type TEXT NOT NULL,              -- strength | metcon | gymnastics | skill | tennis | other
  duration_min REAL NOT NULL,
  avg_hr INTEGER, max_hr INTEGER,
  rpe REAL,                        -- 1..10 (obbligatorio per strength, consigliato sempre)
  load REAL,                       -- calcolato se assente
  notes TEXT DEFAULT '',
  source TEXT NOT NULL DEFAULT 'manuale',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS wods (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  category TEXT NOT NULL DEFAULT 'custom',   -- girl | hero | open | custom
  score_type TEXT NOT NULL,                  -- time | amrap | load | reps
  description TEXT NOT NULL DEFAULT '',
  custom INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS wod_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  wod_id INTEGER NOT NULL REFERENCES wods(id),
  date TEXT NOT NULL,
  score_value REAL NOT NULL,       -- forma normalizzata per confronto
  score_display TEXT NOT NULL,     -- com'è stato inserito (es. "3:45", "12+35")
  scaling TEXT NOT NULL DEFAULT 'rx',  -- rx | scaled | ...
  notes TEXT DEFAULT '',
  is_pr INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meals (
  ts TEXT PRIMARY KEY,             -- ISO datetime locale
  meal TEXT NOT NULL,              -- breakfast | lunch | dinner | snack
  description TEXT DEFAULT '',
  kcal REAL NOT NULL DEFAULT 0,
  protein_g REAL NOT NULL DEFAULT 0,
  carbs_g REAL NOT NULL DEFAULT 0,
  fat_g REAL NOT NULL DEFAULT 0
);
"""


def db_path() -> Path:
    return Path(os.environ.get("BENESSERE_DB", str(DEFAULT_DB)))


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: la connessione cache è usata da thread diversi
    # (Streamlit esegue ogni rerun in un thread nuovo); WAL + accessi brevi.
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def profile_get(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM profile WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def profile_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO profile(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    conn.commit()


def profile_get_float(conn: sqlite3.Connection, key: str, default: float | None = None) -> float | None:
    v = profile_get(conn, key)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default
