"""Seed del catalogo WOD: benchmark classici (le 'Girls' + hero) selezionabili subito."""

from __future__ import annotations

import sqlite3

from . import wods

BENCHMARKS: list[wods.Wod] = [
    wods.Wod("Fran", "time", "girl", "21-15-9: Thruster 42,5/30 kg + Pull-up. Forza volume.", 0),
    wods.Wod("Grace", "time", "girl", "30 Clean & Jerk 61/42,5 kg.", 0),
    wods.Wod("Helen", "time", "girl", "3 round: 400 m corsa + 21 Kettlebell Swing 24/16 kg + 12 Pull-up.", 0),
    wods.Wod("Diane", "time", "girl", "21-15-9: Deadlift 102,5/70 kg + Handstand Push-up.", 0),
    wods.Wod("Elizabeth", "time", "girl", "21-15-9: Clean 52,5/35 kg + Ring Dip.", 0),
    wods.Wod("Karen", "time", "girl", "150 Wall Ball 9/6 kg.", 0),
    wods.Wod("Annie", "time", "girl", "50-40-30-20-10: Double-under + Sit-up.", 0),
    wods.Wod("Cindy", "amrap", "girl", "AMRAP 20': 5 Pull-up + 10 Push-up + 15 Air Squat.", 0),
    wods.Wod("AMRAP 15 Burpees", "amrap", "open", "AMRAP 15': Burpee (stile Open 19.1). Più round possibile.", 0),
    wods.Wod("Murph", "time", "hero", "1,6 km corsa + 100 Pull-up + 200 Push-up + 300 Air Squat + 1,6 km corsa (con giacca 9 kg opzionale).", 0),
    wods.Wod("DT", "time", "hero", "5 round: 12 Deadlift 70/47,5 kg + 9 Hang Power Clean + 6 Jerk.", 0),
    wods.Wod("Back Squat 1RM", "load", "strength", "Massimale Back Squat.", 0),
    wods.Wod("Deadlift 1RM", "load", "strength", "Massimale Deadlift.", 0),
    wods.Wod("Strict Press 1RM", "load", "strength", "Massimale Strict Press.", 0),
    wods.Wod("Snatch 1RM", "load", "strength", "Massimale Snatch.", 0),
    wods.Wod("Clean & Jerk 1RM", "load", "strength", "Massimale Clean & Jerk.", 0),
    wods.Wod("Max Pull-up", "reps", "skill", "Massimo di pull-up strict in una serie.", 0),
    wods.Wod("2k Row", "time", "engine", "2000 metri sul vogatore, tutto fuori.", 0),
]


def seed_if_empty(conn: sqlite3.Connection) -> int:
    existing = conn.execute("SELECT COUNT(*) AS n FROM wods WHERE custom = 0").fetchone()["n"]
    if existing:
        return 0
    added = 0
    for w in BENCHMARKS:
        added += 1 if wods.add_wod(conn, w) else 0
    return added
