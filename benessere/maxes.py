"""Massimali e complex: storico con giorno esatto o solo mese, senza date inventate."""
from __future__ import annotations

from datetime import date
import math
import re
import sqlite3

LIFTS = (
    "Back Squat", "Front Squat", "Deadlift", "Strict Press", "Push Press",
    "Push Jerk", "Split Jerk", "Bench Press", "Overhead Squat", "Snatch",
    "Squat Snatch", "Clean", "Squat Clean", "Power Clean", "Clean & Jerk",
    "Squat Clean & Jerk", "Thruster", "Weighted Pull-up", "Weighted Dip",
)
CATEGORIES = {"lift", "complex"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS strength_maxes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lift TEXT NOT NULL,
    date TEXT NOT NULL,
    weight_kg REAL NOT NULL,
    reps INTEGER NOT NULL DEFAULT 1,
    notes TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manuale',
    category TEXT NOT NULL DEFAULT 'lift',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_strength_maxes_lift_date
ON strength_maxes (lift, date DESC);
"""

def valid_date(day: str) -> str:
    """Preserva YYYY-MM per i risultati con giorno sconosciuto."""
    if re.fullmatch(r"\d{4}-\d{2}", day or ""):
        date.fromisoformat(day + "-01")
        return day
    date.fromisoformat(day)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("Data non valida: YYYY-MM oppure YYYY-MM-DD")
    return day

def readable_date(day: str) -> str:
    months=("gennaio","febbraio","marzo","aprile","maggio","giugno",
            "luglio","agosto","settembre","ottobre","novembre","dicembre")
    if re.fullmatch(r"\d{4}-\d{2}", day):
        return f"{months[int(day[-2:])-1].capitalize()} {day[:4]} (giorno non noto)"
    return date.fromisoformat(day).strftime("%d/%m/%Y")

def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(strength_maxes)")}
    if "category" not in columns:
        conn.execute("ALTER TABLE strength_maxes ADD COLUMN category TEXT NOT NULL DEFAULT 'lift'")
        conn.commit()

def add_max(
    conn: sqlite3.Connection, lift: str, day: str, weight_kg: float,
    *, reps: int = 1, notes: str = "", source: str = "manuale", category: str = "lift",
) -> int:
    lift=lift.strip()
    if not lift or len(lift)>160:
        raise ValueError("Indica un esercizio valido")
    day=valid_date(day)
    if category not in CATEGORIES:
        raise ValueError("Categoria non valida")
    if not math.isfinite(float(weight_kg)) or not (0 < float(weight_kg) <= 1000):
        raise ValueError("Inserisci un carico valido in kg")
    if not 1 <= int(reps) <= 100:
        raise ValueError("Ripetizioni non valide")
    if len(notes)>1000:
        raise ValueError("Note troppo lunghe")
    initialize(conn)
    cur=conn.execute(
        "INSERT INTO strength_maxes(lift,date,weight_kg,reps,notes,source,category) VALUES(?,?,?,?,?,?,?)",
        (lift,day,float(weight_kg),int(reps),notes,source,category),
    )
    conn.commit()
    return int(cur.lastrowid)

def history(conn: sqlite3.Connection, lift: str | None = None, *, category: str | None = None) -> list[sqlite3.Row]:
    initialize(conn)
    clauses=[]
    params=[]
    if lift:
        clauses.append("lift=? COLLATE NOCASE")
        params.append(lift)
    if category:
        clauses.append("category=?")
        params.append(category)
    where=" WHERE "+" AND ".join(clauses) if clauses else ""
    return conn.execute("SELECT * FROM strength_maxes"+where+" ORDER BY date DESC,id DESC",tuple(params)).fetchall()

def best_by_lift(conn: sqlite3.Connection) -> list[dict]:
    """Solo alzate singole realmente dichiarate: i complex NON sono 1RM."""
    selected={}
    for row in history(conn,category="lift"):
        if row["reps"]!=1:continue
        key=row["lift"].casefold()
        prior=selected.get(key)
        if prior is None or row["weight_kg"] > prior["weight_kg"] or (
            row["weight_kg"] == prior["weight_kg"] and row["date"] > prior["date"]
        ):
            selected[key]=dict(row)
    return sorted(selected.values(),key=lambda x:x["lift"].casefold())

def best_complexes(conn: sqlite3.Connection) -> list[dict]:
    selected={}
    for row in history(conn,category="complex"):
        key=row["lift"].casefold()
        prior=selected.get(key)
        if prior is None or row["weight_kg"] > prior["weight_kg"]:
            selected[key]=dict(row)
    return sorted(selected.values(),key=lambda x:x["lift"].casefold())

def delete_max(conn:sqlite3.Connection,result_id:int)->bool:
    initialize(conn)
    row=conn.execute("SELECT id FROM strength_maxes WHERE id=?",(result_id,)).fetchone()
    if not row:return False
    conn.execute("DELETE FROM strength_maxes WHERE id=?",(result_id,))
    conn.commit()
    return True
