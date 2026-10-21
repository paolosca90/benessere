import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from benessere import db as store
from benessere import nutrition, readiness, reminders, seed_wods, workouts, wods


@pytest.fixture()
def conn(tmp_path):
    conn = store.connect(tmp_path / "test.db")
    store.profile_set(conn, "sex", "m")
    store.profile_set(conn, "age", "35")
    store.profile_set(conn, "height_cm", "180")
    store.profile_set(conn, "weight_kg", "80")
    store.profile_set(conn, "goal", "cut")
    store.profile_set(conn, "resting_hr", "55")
    store.profile_set(conn, "sleep_need_h", "8")
    yield conn
    conn.close()


# ---------------- nutrizione ----------------

def test_bmr_mifflin():
    assert nutrition.bmr_mifflin("m", 80, 180, 35) == pytest.approx(1755, abs=1)
    assert nutrition.bmr_mifflin("f", 60, 165, 30) == pytest.approx(1320.25, abs=1)


def test_targets_cut_with_metcon_day(conn):
    from datetime import date

    day = date.today().isoformat()
    workouts.add_workout(conn, workouts.Workout(date=day, type="metcon", duration_min=20, rpe=8))
    t = nutrition.compute_targets(conn)
    assert t.goal == "cut"
    assert t.training_day
    assert t.carb_bonus_g == 100.0
    # proteine da cut: 2.2 g/kg
    assert t.protein_g == pytest.approx(80 * 2.2, abs=1)
    # kcal con bonus carb
    assert t.target_kcal == pytest.approx(round(t.tdee * 0.85 + 400), abs=2)


def test_meal_log_and_totals(conn):
    from datetime import datetime

    ts = datetime(2026, 10, 20, 8, 0, 0).isoformat()
    nutrition.log_meal(conn, "breakfast", 500, 40, 50, 15, "uova+avena", ts=ts)
    nutrition.log_meal(conn, "lunch", 700, 55, 80, 20, "pollo+riso", ts="2026-10-20T13:00:00")
    totals = nutrition.day_totals(conn, "2026-10-20")
    assert totals["count"] == 2
    assert totals["kcal"] == 1200
    assert totals["protein_g"] == 95


def test_meal_reminder(conn):
    from datetime import datetime

    # ore 15: senza pasti → colazione e pranzo in reminder, cena no
    now = datetime(2026, 10, 20, 15, 0)
    rem = reminders.pending_meal_reminders(conn, now)
    meals = {r["meal"] for r in rem}
    assert meals == {"breakfast", "lunch"}
    # dopo pranzo registrato → solo colazione
    nutrition.log_meal(conn, "lunch", 600, 40, 70, 15, ts="2026-10-20T13:30:00")
    rem = reminders.pending_meal_reminders(conn, now)
    assert [r["meal"] for r in rem] == ["breakfast"]


# ---------------- allenamenti ----------------

def test_load_hybrid(conn):
    # metcon con FC: TRIMP-ish
    load_hr = workouts.compute_load(conn, "metcon", 20, rpe=None, avg_hr=160)
    assert load_hr > 0
    # strength: durata × rpe × 0.8
    load_str = workouts.compute_load(conn, "strength", 60, rpe=7, avg_hr=None)
    assert load_str == pytest.approx(60 * 7 * 0.8, abs=0.1)
    # Senza FC né RPE nessun carico inventato.
    assert workouts.compute_load(conn, "metcon", 30, None, None) is None


def test_fitness_fatigue_tsb_drops_after_hard_day(conn):
    from datetime import date, timedelta

    today = date.today()
    for i in range(7, 0, -1):
        workouts.add_workout(
            conn,
            workouts.Workout(date=(today - timedelta(days=i)).isoformat(), type="strength", duration_min=60, rpe=8),
        )
    ff = workouts.fitness_fatigue(conn, today, horizon=10)
    assert ff[-1]["ctl"] > 0
    # dopo una settimana di lavoro la forma (tsb) è negativa
    assert ff[-1]["tsb"] < 0


def test_invalid_workout_type(conn):
    with pytest.raises(ValueError):
        workouts.add_workout(conn, workouts.Workout(date="2026-10-20", type="yoga", duration_min=30, rpe=5))


# ---------------- WOD ----------------

def test_parse_scores():
    assert wods.parse_score("time", "3:45") == 225.0
    assert wods.parse_score("time", "225") == 225.0
    assert wods.parse_score("amrap", "12+35") == pytest.approx(12.35)
    assert wods.parse_score("load", "142.5") == 142.5
    assert wods.parse_score("reps", "87") == 87.0
    with pytest.raises(ValueError):
        wods.parse_score("time", "abc")
    with pytest.raises(ValueError):
        wods.parse_score("time", "3:75")


def test_format_score():
    assert wods.format_score("time", 225) == "3:45"
    assert wods.format_score("amrap", 12.35) == "12+35"


def test_pr_detection(conn):
    seed_wods.seed_if_empty(conn)
    r1 = wods.add_result(conn, "Fran", "2026-10-01", "5:00")
    assert r1["is_pr"]
    r2 = wods.add_result(conn, "Fran", "2026-10-10", "4:30")
    assert r2["is_pr"]  # tempo migliore
    r3 = wods.add_result(conn, "Fran", "2026-10-15", "5:30")
    assert not r3["is_pr"]
    r4 = wods.add_result(conn, "Fran", "2026-10-20", "4:00", scaling="scaled")
    assert r4["is_pr"]  # scaling diverso: PR separato
    prs = wods.prs(conn)
    fran = [p for p in prs if p["wod"] == "Fran"]
    assert {p["scaling"] for p in fran} == {"rx", "scaled"}


def test_amrap_pr_higher_better(conn):
    seed_wods.seed_if_empty(conn)
    assert wods.add_result(conn, "Cindy", "2026-10-01", "15+5")["is_pr"]
    r = wods.add_result(conn, "Cindy", "2026-10-10", "17+2")
    assert r["is_pr"]
    assert not wods.add_result(conn, "Cindy", "2026-10-15", "16")["is_pr"]


def test_seed_benchmarks(conn):
    assert seed_wods.seed_if_empty(conn) > 10
    assert seed_wods.seed_if_empty(conn) == 0  # idempotente
    fran = wods.get_wod(conn, "fran")  # case-insensitive
    assert fran is not None and fran["score_type"] == "time"


# ---------------- readiness ----------------

def test_readiness_graceful_without_data(conn):
    r = readiness.readiness(conn)
    assert r["score"] is None
    assert r["flags"]


def test_readiness_with_sleep_data(conn):
    from datetime import date, timedelta

    today = date.today()
    for i in range(10, 0, -1):
        conn.execute(
            "INSERT OR REPLACE INTO sleeps(night_date, deep_min, light_min, rem_min, source) VALUES(?,?,?,?, 'test')",
            ((today - timedelta(days=i)).isoformat(), 90, 300, 90),
        )
    conn.commit()
    conn.execute(
        "INSERT OR REPLACE INTO sleeps(night_date, deep_min, light_min, rem_min, source) VALUES(?,?,?,?, 'test')",
        (today.isoformat(), 90, 300, 90),
    )
    conn.commit()
    r = readiness.readiness(conn)
    assert r["score"] is not None
    assert "sleep" in r["components"]
