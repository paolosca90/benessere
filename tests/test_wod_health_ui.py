"""Smoke tests with real-like records, empty Health and populated Health."""
import os
from datetime import date, timedelta
from pathlib import Path
from streamlit.testing.v1 import AppTest
from benessere import db, wods, health_sync

ROOT=Path(__file__).resolve().parents[1]/"app.py"

def test_wod_with_real_personal_result_and_benchmarks(tmp_path,monkeypatch):
    dbfile=tmp_path/"user_wod.sqlite3"
    monkeypatch.setenv("BENESSERE_DB",str(dbfile))
    c=db.connect(dbfile)
    wods.add_wod(c,wods.Wod(name="CrossFit 2026-10-21 — 30/30/30 bilanciere",score_type="time",category="custom",description="WOD"))
    wods.add_result(c,"CrossFit 2026-10-21 — 30/30/30 bilanciere","2026-10-21","17:00",scaling="unspecified")
    c.close()
    at=AppTest.from_file(str(ROOT),default_timeout=30)
    at.run()
    at.radio(key="nav").set_value("WOD").run()
    assert not at.exception, [str(e.message) for e in at.exception]
    assert at.radio(key="nav").value == "WOD"
    at.radio(key="nav").set_value("Benchmark").run()
    assert not at.exception, [str(e.message) for e in at.exception]

def test_health_with_monitoring_data(tmp_path,monkeypatch):
    dbfile=tmp_path/"user_health.sqlite3"
    monkeypatch.setenv("BENESSERE_DB",str(dbfile))
    c=db.connect(dbfile)
    day=date.today().isoformat()
    with c:
        c.execute("INSERT INTO days(date,steps,active_kcal,source) VALUES(?,?,?,'health_connect')",
                  (day,7359,400.0))
        c.execute("INSERT INTO sleeps(night_date,total_min,source) VALUES(?,?,'health_connect')",
                  (day,475))
        c.execute("INSERT INTO hrv_daily(night_date,rmssd_ms,source) VALUES(?,?,'zepp')",(day,48.0))
        c.execute("INSERT INTO hr_samples(ts,bpm,source) VALUES(?,?,?)",
                  (f"{day}T10:00:00+00:00",65,"health_connect"))
    c.close()
    at=AppTest.from_file(str(ROOT),default_timeout=30)
    at.run()
    at.radio(key="nav").set_value("Salute").run()
    assert not at.exception, [str(e.message) for e in at.exception]
    texts=" ".join(str(item.value) for item in at.metric)
    assert "7359" in texts or "7,359" in texts
