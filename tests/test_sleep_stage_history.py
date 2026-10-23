"""Only synthetic Health Connect sessions in isolated temporary databases."""
from datetime import date
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from benessere import db, health_sync, sleep_stage_history
from webapp.api.main import app


@pytest.fixture
def conn(tmp_path):
    with db.connect(tmp_path / "stage_history.db") as connection:
        health_sync.initialize(connection)
        yield connection


def packet():
    return {
        "schema": 1,
        "device_id": "synthetic-phone",
        "heart_rates": [{"ts": "2026-10-23T05:00:00Z", "bpm": 59}],
        "sessions": [{
            "kind": "sleep", "id": "night-1", "origin": "com.zepp.example",
            "night_date": "2026-10-23",
            "start": "2026-10-22T23:00:00Z",
            "end": "2026-10-23T06:00:00Z",
            "light_min": 120, "deep_min": 60, "rem_min": 60, "awake_min": 5,
            "stages": [
                {"start": "2026-10-22T23:00:00Z", "end": "2026-10-23T00:00:00Z",
                 "stage": "deep"},
                {"start": "2026-10-23T00:00:00Z", "end": "2026-10-23T02:00:00Z",
                 "stage": "light"},
                {"start": "2026-10-23T02:00:00Z", "end": "2026-10-23T03:00:00Z",
                 "stage": "rem"},
            ],
        }],
    }


def test_stages_are_idempotently_saved_without_inventing_missing_intervals(conn):
    value = packet()
    a = health_sync.ingest_payload(conn, value)
    b = health_sync.ingest_payload(conn, value)
    assert a["received_stage_intervals"] == 3
    assert b["received_stage_intervals"] == 3
    assert conn.execute("SELECT COUNT(*) FROM hc_sleep_stages").fetchone()[0] == 3
    report = sleep_stage_history.report(conn, "2026-10-23")
    assert report["status"] == "timed_history"
    assert report["history_only"] is True
    assert report["live_stage_available"] is False
    assert report["strap_alarm_verified"] is False
    assert report["night_session"]["origin"] == "com.zepp.example"
    assert [x["stage"] for x in report["stages"]] == ["deep", "light", "rem"]
    assert report["stages"][0]["start"].startswith("2026-10-23T01:00:00+02:00")
    assert report["stages"][-1]["end"].startswith("2026-10-23T05:00:00+02:00")


def test_legacy_sync_does_not_erase_preexisting_timed_stages(conn):
    value = packet()
    health_sync.ingest_payload(conn, value)
    second = deepcopy(value)
    del second["sessions"][0]["stages"]
    health_sync.ingest_payload(conn, second)
    assert conn.execute("SELECT COUNT(*) FROM hc_sleep_stages").fetchone()[0] == 3


def test_no_sleep_stages_means_history_not_live(conn):
    value = packet()
    del value["sessions"][0]["stages"]
    health_sync.ingest_payload(conn, value)
    report = sleep_stage_history.report(conn, "2026-10-23")
    assert report["status"] == "summary_only"
    assert report["stages"] == []
    assert report["night_session"]["stage_minutes"]["light"] == 120
    assert not report["live_stage_available"]


@pytest.mark.parametrize("stages", [
    [{"start": "2026-10-22T22:00:00Z", "end": "2026-10-22T23:10:00Z", "stage": "deep"}],
    [{"start": "2026-10-22T23:00:00Z", "end": "2026-10-23T00:00:00Z", "stage": "deep"},
     {"start": "2026-10-22T23:30:00Z", "end": "2026-10-23T01:00:00Z", "stage": "light"}],
    [{"start": "2026-10-22T23:00:00Z", "end": "2026-10-23T00:00:00Z", "stage": "fake"}],
    [{"start": "2026-10-22T23:00:00", "end": "2026-10-23T00:00:00Z", "stage": "deep"}],
    [{"start": "2026-10-22T23:00:00Z", "end": "2026-10-22T23:00:00Z", "stage": "deep"}],
])
def test_invalid_phases_are_isolated_and_do_not_block_other_measurements(conn, stages):
    value = packet()
    value["sessions"][0]["stages"] = stages
    outcome = health_sync.ingest_payload(conn, value)
    assert outcome["skipped_stage_sessions"] == 1
    assert outcome["received_stage_intervals"] == 0
    assert conn.execute("SELECT COUNT(*) FROM hc_events").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM hc_sleep_stages").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM hr_samples").fetchone()[0] == 1


def test_explicit_empty_update_replaces_timed_stages_but_never_fabricates(conn):
    value = packet()
    health_sync.ingest_payload(conn, value)
    value["sessions"][0]["stages"] = []
    health_sync.ingest_payload(conn, value)
    assert conn.execute("SELECT COUNT(*) FROM hc_sleep_stages").fetchone()[0] == 0


def test_no_session_returns_clear_missing_status(conn):
    r = sleep_stage_history.report(conn, "2026-10-22")
    assert r["status"] == "missing"
    assert r["night_session"] is None
    assert r["stages"] == []


def test_new_sleep_stage_endpoint_requires_auth_and_is_history_only(tmp_path, monkeypatch):
    monkeypatch.setenv("BENESSERE_DB", str(tmp_path / "web.db"))
    monkeypatch.setenv("BENESSERE_WEB_API_TOKEN", "x" * 40)
    with TestClient(app) as client:
        assert client.get("/v1/sleep-stage-history?day=2026-10-23").status_code == 401
        response = client.get("/v1/sleep-stage-history?day=2026-10-23",
                              headers={"Authorization": "Bearer " + "x" * 40})
        assert response.status_code == 200
        assert response.json()["status"] == "missing"
        assert response.json()["live_stage_available"] is False
