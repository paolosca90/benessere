"""Planner alimentare: tipo di giornata reale, mai tennis fissato al sabato.

I target sono stime iniziali per una fase di crescita muscolare per 81 kg,
non equivalgono al dispendio misurato. Si confermano/aggiornano in app.
"""
from __future__ import annotations

from datetime import date
import sqlite3

from . import db

MODES = {
    "crossfit_hard": "CrossFit intenso",
    "crossfit_light": "CrossFit leggero / pesi",
    "tennis": "Tennis",
    "double": "Doppia sessione (CrossFit/pesi + tennis)",
    "rest": "Riposo confermato",
    "unspecified": "Da specificare",
}
# Proteine, carboidrati e grassi, non kcal indipendenti: kcal derivate dai macro.
MACROS = {
    "crossfit_hard": (165, 420, 80),
    "crossfit_light": (165, 370, 80),
    "tennis": (165, 395, 80),
    "double": (165, 455, 85),
    "rest": (165, 305, 85),
}
SCHEMA = """CREATE TABLE IF NOT EXISTS nutrition_day_modes (
    date TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);"""

def initialize(conn: sqlite3.Connection):
    conn.execute(SCHEMA)

def save_mode(conn: sqlite3.Connection, day: str, mode: str):
    date.fromisoformat(day)
    if mode not in MODES:
        raise ValueError("Tipo giornata non valido")
    initialize(conn)
    if mode == "unspecified":
        conn.execute("DELETE FROM nutrition_day_modes WHERE date=?", (day,))
    else:
        conn.execute(
            "INSERT INTO nutrition_day_modes(date,mode,source) VALUES(?,?, 'manual') "
            "ON CONFLICT(date) DO UPDATE SET mode=excluded.mode, source='manual', updated_at=datetime('now')",
            (day, mode),
        )
    conn.commit()

def day_mode(conn: sqlite3.Connection, day: str) -> dict:
    """Prima modalità dichiarata; poi deduzione dalle sole sessioni registrate.

    Senza allenamenti, il giorno NON viene marcato come riposo automaticamente.
    Una sessione genericamente 'other' non certifica CrossFit intenso.
    """
    date.fromisoformat(day)
    initialize(conn)
    explicit = conn.execute(
        "SELECT mode FROM nutrition_day_modes WHERE date=?", (day,)
    ).fetchone()
    if explicit:
        return {"mode": explicit["mode"], "source": "manual"}
    rows = conn.execute(
        "SELECT type FROM workouts WHERE date=?", (day,)
    ).fetchall()
    types={row["type"] for row in rows}
    if "tennis" in types and any(t != "tennis" for t in types):
        return {"mode":"double","source":"workouts"}
    if "tennis" in types:
        return {"mode":"tennis","source":"workouts"}
    if "metcon" in types or "gymnastics" in types:
        return {"mode":"crossfit_hard","source":"workouts"}
    if "strength" in types or "skill" in types:
        if "other" not in types:
            return {"mode":"crossfit_light","source":"workouts"}
    return {"mode":"unspecified","source":"missing"}

def provisional_bulk_target(conn: sqlite3.Connection, day: str) -> dict | None:
    """Indicazione concordata, riferita al peso iniziale 81 kg.

    I valori non stimano la spesa del dispositivo e non si sommano ad active_kcal.
    In un giorno non classificato non inventare il tipo di allenamento.
    """
    if db.profile_get(conn,"goal") != "bulk":
        return None
    state=day_mode(conn,day)
    mode=state["mode"]
    if mode not in MACROS:
        return None
    p,c,f=MACROS[mode]
    return {
        "date":day, "mode":mode, "label":MODES[mode],
        "mode_source":state["source"],
        "target_kcal":p*4+c*4+f*9,
        "protein_g":p, "carbs_g":c, "fat_g":f,
        "source":"initial_estimate_81kg",
    }
