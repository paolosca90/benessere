"""Physiological load is derived only from historical, timestamped measurements.

All samples in these tests are synthetic and remain in isolated temporary SQLite.
"""
from datetime import date, datetime, timedelta, timezone

from benessere import db, physiological_load
from webapp.api.main import app
from fastapi.testclient import TestClient


def _workout(conn, *, clock="09:00", duration=25.6667, rpe=4):
    c = conn.execute(
        "INSERT INTO workouts(date,type,duration_min,start_time,rpe,notes) "
        "VALUES(?,?,?,?,?,?)",
        ("2026-10-23", "other", duration, clock, rpe, "Synthetic test")
    )
    conn.commit()
    return c.lastrowid


def _samples(conn, minutes, bpm=150, source="health_connect"):
    # October 23, 2026 in Rome is UTC+02 until the DST switch on October 25.
    start=datetime(2026, 10, 23, 7, 0, tzinfo=timezone.utc)
    for minute in minutes:
        when = start + timedelta(minutes=minute)
        conn.execute("INSERT INTO hr_samples(ts,bpm,source) VALUES(?,?,?)",
                     (when.isoformat(timespec="milliseconds"), bpm+minute%12, source))
    conn.commit()


def test_wod_hr_uses_local_start_and_real_coverage(tmp_path):
    with db.connect(tmp_path/"physio.db") as conn:
        wid=_workout(conn)
        _samples(conn, range(26))
        report=physiological_load.report(conn, date(2026,10,23))
        w=report["workouts"][0]
        assert w["id"]==wid
        assert w["rpe"]==4
        assert w["session_rpe_au"]==102.7
        assert report["training"]["session_rpe_au"]==102.7
        assert w["hr"]["sample_count"]==26
        assert w["hr"]["status"]=="sufficient"
        assert w["hr"]["sampled_minutes"]==26
        assert w["hr"]["minute_bin_coverage_pct"]==100.0
        assert w["hr"]["max_bpm"]==161
        assert w["hr"]["sources"]==["health_connect"]
        assert len(w["hr"]["series"])==26


def test_sparse_samples_do_not_fake_continuous_hr(tmp_path):
    with db.connect(tmp_path/"physio.db") as conn:
        _workout(conn)
        _samples(conn, [0, 1, 15, 22])
        w=physiological_load.report(conn,date(2026,10,23))["workouts"][0]
        assert w["hr"]["status"]=="partial"
        assert w["hr"]["minute_bin_coverage_pct"]<20
        assert w["hr"]["series"][2]["bpm"] is None
        assert w["hr"]["series"][15]["bpm"] is not None
        assert "parziale" in w["hr"]["reason"].lower()


def test_unknown_workout_start_does_not_assign_any_heart_rate(tmp_path):
    with db.connect(tmp_path/"physio.db") as conn:
        _workout(conn,clock=None)
        _samples(conn, range(26))
        w=physiological_load.report(conn,date(2026,10,23))["workouts"][0]
        assert w["hr"]["status"]=="time_missing"
        assert w["hr"]["average_bpm"] is None


def test_hr_without_samples_and_rpe_absent_stays_missing(tmp_path):
    with db.connect(tmp_path/"physio.db") as conn:
        _workout(conn,rpe=None)
        report=physiological_load.report(conn,date(2026,10,23))
        assert report["training"]["session_rpe_au"] is None
        assert report["workouts"][0]["hr"]["status"]=="unavailable"
        assert report["workouts"][0]["hr"]["average_bpm"] is None
        assert report["day"]["hrv_rmssd_ms"] is None
        assert report["baselines"]["hrv"]["median"] is None


def test_prior_14_days_baselines_require_seven_distinct_days(tmp_path):
    with db.connect(tmp_path/"physio.db") as conn:
        for i in range(1,8):
            d=(date(2026,10,23)-timedelta(days=i)).isoformat()
            conn.execute("INSERT INTO hrv_daily(night_date,rmssd_ms,source) VALUES(?,?,'health_connect')",(d,45+i))
            conn.execute("INSERT INTO days(date,resting_hr,source) VALUES(?,?,'health_connect')",(d,50+i))
        conn.execute("INSERT INTO hrv_daily(night_date,rmssd_ms,source) VALUES('2026-10-23',44,'health_connect')")
        conn.execute("INSERT INTO days(date,resting_hr,steps,active_kcal,source) VALUES('2026-10-23',55,9999,400,'health_connect')")
        conn.commit()
        report=physiological_load.report(conn,date(2026,10,23))
        assert report["baselines"]["hrv"]["median"]==49
        assert report["baselines"]["resting_hr"]["median"]==54
        assert report["day"]["steps"]==9999
        assert report["day"]["hrv_rmssd_ms"]==44


def test_api_is_authenticated_and_returns_missingness(tmp_path,monkeypatch):
    monkeypatch.setenv("BENESSERE_DB",str(tmp_path/"api.db"))
    monkeypatch.setenv("BENESSERE_WEB_API_TOKEN","x"*40)
    with TestClient(app) as client:
        assert client.get("/v1/physiological-load?day=2026-10-23").status_code==401
        res=client.get("/v1/physiological-load?day=2026-10-23",
                       headers={"Authorization":"Bearer "+"x"*40})
        assert res.status_code==200,res.text
        obj=res.json()
        assert obj["date"]=="2026-10-23"
        assert obj["day"]["historical_hr_samples"]==0
        assert obj["training"]["session_rpe_au"] is None
        assert obj["day"]["sleep_minutes"] is None
