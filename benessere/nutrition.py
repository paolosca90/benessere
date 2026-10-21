"""Nutrizione: TDEE adattivo, target macro con periodizzazione carboidrati, log pasti."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta

from . import db as store

# Finastre pasto: (nome, ora limite oltre la quale "manca")
DEFAULT_MEAL_WINDOWS = {"breakfast": 10.0, "lunch": 14.0, "dinner": 21.5}
TRAINING_TYPES_CARB_HIGH = {"metcon", "gymnastics", "tennis"}


@dataclass
class Targets:
    date: str
    tdee: float
    goal: str
    target_kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float
    carb_bonus_g: float
    training_day: bool

    def as_dict(self) -> dict:
        return asdict(self)


def bmr_mifflin(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + 5 if sex.startswith("m") else base - 161


def avg_active_kcal(conn: sqlite3.Connection, today: date, window: int = 7) -> float:
    start = (today - timedelta(days=window - 1)).isoformat()
    row = conn.execute(
        "SELECT AVG(active_kcal) AS a FROM days WHERE date >= ? AND active_kcal IS NOT NULL",
        (start,),
    ).fetchone()
    return float(row["a"] or 0.0)


def training_today(conn: sqlite3.Connection, day: str) -> tuple[bool, list[str]]:
    rows = conn.execute("SELECT type FROM workouts WHERE date = ?", (day,)).fetchall()
    types = [r["type"] for r in rows]
    return bool(types), types


def profile_missing(conn: sqlite3.Connection) -> list[str]:
    """Dati necessari al target: nessun valore anagrafico di fantasia."""
    required = {"sex": "sesso", "weight_kg": "peso", "height_cm": "altezza", "age": "età", "goal": "obiettivo"}
    return [label for key, label in required.items() if store.profile_get(conn, key) in (None, "")]


def compute_targets(conn: sqlite3.Connection, day: date | None = None) -> Targets | None:
    if profile_missing(conn):
        return None
    day = day or date.today()
    day_s = day.isoformat()

    sex = store.profile_get(conn, "sex")
    weight = store.profile_get_float(conn, "weight_kg")
    height = store.profile_get_float(conn, "height_cm")
    age = int(store.profile_get_float(conn, "age"))
    goal = store.profile_get(conn, "goal")

    bmr = bmr_mifflin(sex, weight, height, age)
    tdee = bmr * 1.2 + avg_active_kcal(conn, day)  # base sedentaria + attività reale media

    goal_delta = {"cut": -0.15, "maintain": 0.0, "bulk": 0.10}.get(goal, 0.0)
    kcal = tdee * (1 + goal_delta)

    protein_per_kg = {"cut": 2.2, "maintain": 1.9, "bulk": 2.0}.get(goal, 1.9)
    protein = weight * protein_per_kg
    fat = weight * 0.9

    trained, types = training_today(conn, day_s)
    carb_bonus = 0.0
    if any(t in TRAINING_TYPES_CARB_HIGH for t in types):
        carb_bonus = 100.0
    elif "strength" in types:
        carb_bonus = 50.0
    kcal += carb_bonus * 4  # i carboidrati extra aggiungono kcal

    kcal_from_pf = protein * 4 + fat * 9
    carbs = max((kcal - kcal_from_pf) / 4, 50.0)

    return Targets(
        date=day_s,
        tdee=round(tdee),
        goal=goal,
        target_kcal=round(kcal),
        protein_g=round(protein),
        carbs_g=round(carbs),
        fat_g=round(fat),
        carb_bonus_g=carb_bonus,
        training_day=trained,
    )


def log_meal(
    conn: sqlite3.Connection,
    meal: str,
    kcal: float = 0.0,
    protein_g: float = 0.0,
    carbs_g: float = 0.0,
    fat_g: float = 0.0,
    description: str = "",
    ts: str | None = None,
) -> str:
    ts = ts or datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT OR REPLACE INTO meals(ts, meal, description, kcal, protein_g, carbs_g, fat_g) "
        "VALUES(?,?,?,?,?,?,?)",
        (ts, meal, description, kcal, protein_g, carbs_g, fat_g),
    )
    conn.commit()
    return ts


def meals_for_day(conn: sqlite3.Connection, day: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM meals WHERE substr(ts, 1, 10) = ? ORDER BY ts", (day,)
    ).fetchall()


def day_totals(conn: sqlite3.Connection, day: str) -> dict:
    rows = meals_for_day(conn, day)
    totals = {"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0, "count": len(rows)}
    for r in rows:
        totals["kcal"] += r["kcal"] or 0
        totals["protein_g"] += r["protein_g"] or 0
        totals["carbs_g"] += r["carbs_g"] or 0
        totals["fat_g"] += r["fat_g"] or 0
    for k in ("kcal", "protein_g", "carbs_g", "fat_g"):
        totals[k] = round(totals[k], 1)
    return totals


def meal_windows() -> dict[str, float]:
    """Ore limite per pasto; sovrascrivibili da profilo (keys: window_breakfast, ...)."""
    return DEFAULT_MEAL_WINDOWS
