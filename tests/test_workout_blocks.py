"""Correzioni idempotenti di allenamenti importati e cronologia dei blocchi."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from benessere import db, workout_details
from sheets_bridge import apply_event

SRC=Path(__file__).resolve().parents[1]/"app.py"

@pytest.fixture()
def conn(tmp_path):
    c=db.connect(tmp_path/"test.sqlite3")
    yield c
    c.close()

def original():
    return {
      "date":"2026-04-01","type":"other","duration_min":60,
      "notes":"Sessione con EMOM e tre segmenti di WOD.",
      "wod":{"name":"WOD sintetico test","category":"custom","score_type":"time",
             "description":"Tre segmenti","score":"17:00"}
    }

def revision():
    return {
      "update_of":"workout_synthetic_01","date":"2026-04-01","start_time":"08:00",
      "duration_min":60,
      "notes":"EMOM 00-10 forza; poi pull; WOD A/B/C con RPE 5, 5 e 7.",
      "wod_notes":"RPE percepita: A 5/10, B 5/10, C 7/10. I 5, 5 e 7 non sono minuti. Partenze a +0, +6 e +12 dal WOD.",
      "blocks":[
        {"phase":"strength","label":"EMOM 0–10","exercise":"Squat","sets":10,
         "repetitions":1,"weight_kg":80,"start_offset_min":0,"end_offset_min":10,
         "reported_duration_min":10,"time_reference":"workout"},
        {"phase":"strength","label":"Pulls 5x1","exercise":"Pulls","sets":5,
         "repetitions":1,"weight_kg":80,"time_reference":"unspecified"},
        {"phase":"wod","label":"WOD A","exercise":"Snatch","repetitions":30,
         "weight_kg":45,"start_offset_min":0,"rpe":5,
         "time_reference":"wod"},
        {"phase":"wod","label":"WOD B","exercise":"Clean and jerk","repetitions":30,
         "weight_kg":45,"start_offset_min":6,"rpe":5,
         "time_reference":"wod"},
        {"phase":"wod","label":"WOD C","exercise":"Thrusters","repetitions":30,
         "weight_kg":45,"start_offset_min":12,"rpe":7,
         "time_reference":"wod"}
      ]
    }

def test_update_preserves_original_wod_and_single_session(conn):
    first=apply_event(conn,"workout_synthetic_01","workout",original())
    revised=apply_event(conn,"workout_revision_01","workout",revision())
    assert revised["status"]=="saved"
    assert revised["result"]["workout_id"]==first["result"]["workout_id"]
    assert revised["result"]["wod_result_id"]==first["result"]["wod_result_id"]
    assert revised["result"]["blocks_updated"]==5
    assert revised["result"]["timeline_warnings"]==[]
    w=conn.execute("SELECT * FROM workouts").fetchone()
    assert w["start_time"]=="08:00"
    assert w["duration_min"]==60
    blocks=workout_details.blocks_for(conn,w["id"])
    assert len(blocks)==5
    assert [b["reported_duration_min"] for b in blocks[2:]]==[None,None,None]
    assert [b["rpe"] for b in blocks[2:]]==[5,5,7]
    assert conn.execute("SELECT COUNT(*) FROM workouts").fetchone()[0]==1
    assert conn.execute("SELECT score_display FROM wod_results").fetchone()[0]=="17:00"
    assert apply_event(conn,"workout_revision_01","workout",revision())["status"]=="duplicate"
    assert len(workout_details.blocks_for(conn,w["id"]))==5

def test_invalid_revision_is_atomic(conn):
    apply_event(conn,"workout_synthetic_01","workout",original())
    good=revision()
    good["blocks"][2]["weight_kg"]=-4
    with pytest.raises(ValueError):
        apply_event(conn,"workout_revision_bad","workout",good)
    assert conn.execute("SELECT start_time FROM workouts").fetchone()[0] is None
    assert conn.execute("SELECT COUNT(*) FROM workout_blocks").fetchone()[0]==0

def test_rpe_cannot_be_outside_1_to_10(conn):
    apply_event(conn,"workout_synthetic_01","workout",original())
    bad=revision()
    bad["blocks"][3]["rpe"]=11
    with pytest.raises(ValueError, match="RPE"):
        apply_event(conn,"workout_revision_wrong_rpe","workout",bad)
    assert conn.execute("SELECT COUNT(*) FROM workout_blocks").fetchone()[0]==0


def test_existing_workout_blocks_table_migrates_to_rpe(tmp_path):
    import sqlite3
    path=tmp_path/"legacy.sqlite3"
    previous=sqlite3.connect(path)
    previous.execute("""
        CREATE TABLE workout_blocks(
            id INTEGER PRIMARY KEY,
            workout_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            phase TEXT NOT NULL,
            label TEXT NOT NULL,
            exercise TEXT NOT NULL,
            repetitions INTEGER,
            sets INTEGER,
            weight_kg REAL,
            start_offset_min REAL,
            end_offset_min REAL,
            reported_duration_min REAL,
            time_reference TEXT NOT NULL DEFAULT 'workout',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(workout_id,position)
        )""")
    previous.commit()
    previous.close()
    upgraded=db.connect(path)
    try:
        assert "rpe" in {col["name"] for col in upgraded.execute("PRAGMA table_info(workout_blocks)")}
    finally:
        upgraded.close()


def test_wod_and_training_pages_show_session_blocks(tmp_path,monkeypatch):
    dbfile=tmp_path/"app.sqlite3"
    monkeypatch.setenv("BENESSERE_DB",str(dbfile))
    c=db.connect(dbfile)
    apply_event(c,"workout_synthetic_01","workout",original())
    apply_event(c,"workout_revision_01","workout",revision())
    c.close()
    app=AppTest.from_file(str(SRC),default_timeout=30)
    app.run()
    app.radio(key="nav").set_value("Allenamenti").run()
    assert not app.exception, [str(x.message) for x in app.exception]
    app.radio(key="nav").set_value("WOD").run()
    assert not app.exception, [str(x.message) for x in app.exception]
    assert len(app.warning) == 0
