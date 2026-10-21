"""I giorni con tennis variabile non sono automaticamente ogni sabato."""
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest
from benessere import db, nutrition_schedule, workouts


@pytest.fixture
def conn(tmp_path):
    c=db.connect(tmp_path/"dailyplan.sqlite3")
    db.profile_set(c,"goal","bulk")
    db.profile_set(c,"weight_kg","81")
    yield c
    c.close()


def test_tennis_on_saturday_is_not_assumed(conn):
    # Un sabato senza allenamenti registrati non è automaticamente tennis o riposo.
    assert nutrition_schedule.day_mode(conn,"2026-10-24")=={"mode":"unspecified","source":"missing"}
    assert nutrition_schedule.provisional_bulk_target(conn,"2026-10-24") is None


def test_tennis_after_light_crossfit_is_double(conn):
    workouts.add_workout(conn,workouts.Workout(date="2026-10-24",type="strength",duration_min=50,rpe=5))
    workouts.add_workout(conn,workouts.Workout(date="2026-10-24",type="tennis",duration_min=90,rpe=7))
    state=nutrition_schedule.day_mode(conn,"2026-10-24")
    assert state=={"mode":"double","source":"workouts"}
    target=nutrition_schedule.provisional_bulk_target(conn,"2026-10-24")
    assert target["target_kcal"]==3245
    assert target["protein_g"]==165 and target["carbs_g"]==455 and target["fat_g"]==85


def test_tennis_elsewhere_and_not_double_counted(conn):
    workouts.add_workout(conn,workouts.Workout(date="2026-10-27",type="tennis",duration_min=90,rpe=6))
    assert nutrition_schedule.day_mode(conn,"2026-10-27")["mode"]=="tennis"
    assert nutrition_schedule.provisional_bulk_target(conn,"2026-10-27")["target_kcal"]==2960
    workouts.add_workout(conn,workouts.Workout(date="2026-10-27",type="metcon",duration_min=50,rpe=7))
    assert nutrition_schedule.day_mode(conn,"2026-10-27")["mode"]=="double"


def test_intensity_and_override(conn):
    workouts.add_workout(conn,workouts.Workout(date="2026-10-25",type="other",duration_min=50,rpe=None))
    assert nutrition_schedule.day_mode(conn,"2026-10-25")["mode"]=="unspecified"
    nutrition_schedule.save_mode(conn,"2026-10-25","crossfit_hard")
    assert nutrition_schedule.day_mode(conn,"2026-10-25")["mode"]=="crossfit_hard"
    assert nutrition_schedule.provisional_bulk_target(conn,"2026-10-25")["target_kcal"]==3060
    nutrition_schedule.save_mode(conn,"2026-10-25","unspecified")
    assert nutrition_schedule.day_mode(conn,"2026-10-25")["mode"]=="unspecified"


def test_confirmed_rest_only_when_declared(conn):
    nutrition_schedule.save_mode(conn,"2026-10-26","rest")
    assert nutrition_schedule.day_mode(conn,"2026-10-26")["mode"]=="rest"
    assert nutrition_schedule.provisional_bulk_target(conn,"2026-10-26")["target_kcal"]==2645


def test_nutrition_planner_page_with_a_double_session(tmp_path,monkeypatch):
    path=tmp_path/"ui.sqlite3"
    monkeypatch.setenv("BENESSERE_DB",str(path))
    c=db.connect(path)
    db.profile_set(c,"goal","bulk")
    db.profile_set(c,"weight_kg","81")
    day=date.today().isoformat()
    workouts.add_workout(c,workouts.Workout(date=day,type="tennis",duration_min=90,rpe=6))
    workouts.add_workout(c,workouts.Workout(date=day,type="strength",duration_min=50,rpe=6))
    c.close()
    app=AppTest.from_file(str(__import__("pathlib").Path(__file__).resolve().parents[1]/"app.py"),default_timeout=30)
    app.run()
    app.radio(key="nav").set_value("Alimentazione").run()
    assert not app.exception,[str(x.message) for x in app.exception]
    assert any(m.label=="Energia" and "0" in str(m.value) for m in app.metric)
