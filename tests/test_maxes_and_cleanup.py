"""Massimali, migrazione prudente e assenza di profili fittizi."""
from pathlib import Path
import pytest
from benessere import db, housekeeping, maxes, nutrition, seed_wods, wods, workouts
from sheets_bridge import apply_event


@pytest.fixture()
def c(tmp_path):
    connection = db.connect(tmp_path / "benessere.db")
    yield connection
    connection.close()


def test_no_targets_from_fake_defaults(c):
    assert nutrition.compute_targets(c) is None
    assert set(nutrition.profile_missing(c)) == {"sesso","peso","altezza","età","obiettivo"}


def test_max_history_and_true_one_rep_record(c):
    maxes.add_max(c, "Back Squat", "2026-10-21", 90, reps=1)
    maxes.add_max(c, "Back Squat", "2026-09-01", 110, reps=3)
    maxes.add_max(c, "Back Squat", "2026-10-20", 100, reps=1)
    rows = maxes.history(c, "Back Squat")
    assert [x["date"] for x in rows] == ["2026-10-21","2026-10-20","2026-09-01"]
    best = maxes.best_by_lift(c)
    assert len(best) == 1 and best[0]["weight_kg"] == 100
    assert best[0]["reps"] == 1
    with pytest.raises(ValueError):
        maxes.add_max(c, "Snatch", "2026-10-21", -10)


def test_bridge_max_is_idempotent(c):
    payload={"date":"2026-10-21","lift":"Snatch","weight_kg":65,"reps":1,"notes":"effettivo"}
    r=apply_event(c,"max_20261021_snatch","max",payload)
    assert r["status"] == "saved"
    assert apply_event(c,"max_20261021_snatch","max",payload)["status"]=="duplicate"
    assert len(maxes.history(c))==1


def test_cleanup_preserves_results_and_backs_up(c, tmp_path):
    seed_wods.seed_if_empty(c)
    # Fran è un benchmark con risultato reale; Grace è solo una definizione seed.
    wods.add_result(c,"Fran","2026-10-10","4:30")
    wods.add_wod(c,wods.Wod("Mio WOD","time",custom=1))
    with c:
        c.execute("INSERT INTO meals(ts,meal,description,kcal,protein_g,carbs_g,fat_g) VALUES(?,?,?,?,?,?,?)",
                  ("2026-10-21T13:00:00","lunch","pasta",500,20,80,10))
        c.execute("INSERT INTO workouts(date,type,duration_min,load,source) VALUES(?,?,?,?,?)",
                  ("2026-10-21","other",60,180,"chatgpt_sheets"))
    before=housekeeping.preview(c)
    assert before["seed_rows_without_results"] > 5
    assert before["synthetic_training_loads"] == 1
    cleaned=housekeeping.migrate(c,tmp_path/"benessere.db")
    assert cleaned == before
    assert wods.get_wod(c,"Grace") is None
    assert wods.get_wod(c,"Fran") is not None
    assert len(wods.results_for(c,"Fran"))==1
    assert wods.get_wod(c,"Mio WOD") is not None
    assert c.execute("SELECT COUNT(*) FROM meals").fetchone()[0]==1
    assert c.execute("SELECT load FROM workouts").fetchone()[0] is None
    assert list(tmp_path.glob("benessere.backup-before-cleanup-*.sqlite3"))
    assert housekeeping.migrate(c,tmp_path/"benessere.db")=={
        "seed_rows_without_results":0,"synthetic_training_loads":0
    }
