"""Allenamenti: log sessioni CrossFit/tennis, carico ibrido, fitness-fatigue (CTL/ATL/TSB)."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, timedelta

VALID_TYPES = {"strength", "metcon", "gymnastics", "skill", "tennis", "other"}

# Il carico cardio è affidabile con la FC; per forza/gymnastics la FC da polso
# è inaffidabile sotto sforzo → durata × RPE.
HR_BASED_TYPES = {"metcon", "tennis", "other"}


@dataclass
class Workout:
    date: str
    type: str
    duration_min: float
    rpe: float | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    load: float | None = None
    notes: str = ""
    source: str = "manuale"
    id: int | None = None


def estimate_hr_max(conn: sqlite3.Connection) -> int | None:
    """FC max funzionale: la più alta osservata nelle sessioni, altrimenti stima età."""
    row = conn.execute("SELECT MAX(max_hr) AS m FROM workouts WHERE max_hr IS NOT NULL").fetchone()
    if row and row["m"]:
        return int(row["m"])
    from . import db as store

    age = store.profile_get_float(conn, "age")
    return int(220 - age) if age is not None else None


def compute_load(
    conn: sqlite3.Connection,
    wtype: str,
    duration_min: float,
    rpe: float | None,
    avg_hr: int | None,
) -> float:
    """Carico ibrido.

    - metcon/tennis/other con FC: TRIMP di Banister semplificato
      (durata × frazione di riserva cardiaca × fattore intensità).
    - senza FC: durata × RPE × 0.6.
    - strength/gymnastics/skill: durata × RPE × 0.8 (l'RPE è la verità).
    """
    if duration_min <= 0:
        return 0.0
    if wtype in HR_BASED_TYPES and avg_hr:
        hr_max = estimate_hr_max(conn)
        from . import db as store

        rhr = store.profile_get_float(conn, "resting_hr")
        if hr_max is not None and rhr is not None:
            hrr = max(hr_max - rhr, 30)
            intensity = (avg_hr - rhr) / hrr
            intensity = min(max(intensity, 0.1), 1.2)
            return round(duration_min * intensity * 1.2, 1)
    if rpe:
        factor = 0.8 if wtype in {"strength", "gymnastics", "skill"} else 0.6
        return round(duration_min * rpe * factor, 1)
    # Nessun dato di intensità reale: non inventare un carico neutro.
    return None


def add_workout(conn: sqlite3.Connection, w: Workout) -> int:
    if w.type not in VALID_TYPES:
        raise ValueError(f"tipo sessione non valido: {w.type} (validi: {sorted(VALID_TYPES)})")
    if not w.source.startswith("zepp"):
        w.load = compute_load(conn, w.type, w.duration_min, w.rpe, w.avg_hr)
    cur = conn.execute(
        "INSERT INTO workouts(date, type, duration_min, avg_hr, max_hr, rpe, load, notes, source) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (w.date, w.type, w.duration_min, w.avg_hr, w.max_hr, w.rpe, w.load, w.notes, w.source),
    )
    conn.commit()
    return int(cur.lastrowid)


def workouts_between(conn: sqlite3.Connection, start: str, end: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM workouts WHERE date BETWEEN ? AND ? ORDER BY date, id", (start, end)
    ).fetchall()


def fitness_fatigue(conn: sqlite3.Connection, today: date | None = None, horizon: int = 90) -> list[dict]:
    """CTL (EWMA 42g), ATL (EWMA 7g), TSB = CTL-ATL per ogni giorno dell'orizzonte."""
    today = today or date.today()
    start = today - timedelta(days=horizon - 1)
    rows = workouts_between(conn, start.isoformat(), today.isoformat())
    load_by_day: dict[str, float] = {}
    for r in rows:
        load_by_day[r["date"]] = load_by_day.get(r["date"], 0.0) + (r["load"] or 0.0)

    ctl = atl = 0.0
    out: list[dict] = []
    for i in range(horizon):
        d = start + timedelta(days=i)
        load = load_by_day.get(d.isoformat(), 0.0)
        ctl += (load - ctl) * (1 - pow(0.5, 1 / 42)) if ctl or load else ctl
        atl += (load - atl) * (1 - pow(0.5, 1 / 7)) if atl or load else atl
        out.append(
            {"date": d.isoformat(), "load": round(load, 1), "ctl": round(ctl, 1), "atl": round(atl, 1), "tsb": round(ctl - atl, 1)}
        )
    return out


def weekly_volume_by_type(conn: sqlite3.Connection, weeks: int = 6) -> dict[str, float]:
    """Minuti per tipo nelle ultime N settimane (per bilanciare forza/metcon)."""
    start = (date.today() - timedelta(days=weeks * 7 - 1)).isoformat()
    rows = conn.execute(
        "SELECT type, SUM(duration_min) AS m FROM workouts WHERE date >= ? GROUP BY type", (start,)
    ).fetchall()
    return {r["type"]: round(r["m"] or 0.0, 0) for r in rows}
