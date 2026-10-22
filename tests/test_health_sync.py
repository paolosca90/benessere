import json
import threading
from datetime import date, timedelta
from http.client import HTTPConnection

import pytest

from benessere import db, health_sync, readiness
from sync_server import SyncHTTPServer


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "health.db")
    health_sync.initialize(c)
    db.profile_set(c, "sleep_need_h", "8")
    yield c
    c.close()


def sample_data():
    now = date.today()
    yesterday = (now - timedelta(days=1)).isoformat()
    return {
        "schema": 1, "device_id": "test-phone",
        "days": [{"date": yesterday, "steps": 3000, "active_kcal": 500.0, "total_kcal": 2300.0}],
        "heart_rates": [{"ts": f"{yesterday}T10:00:00Z", "bpm": 65},
                        {"ts": f"{yesterday}T10:00:01Z", "bpm": 70}],
        "sessions": [
            {"kind": "sleep", "id": "sleep1", "origin": "com.zepp", "start": f"{yesterday}T00:00:00Z",
             "end": f"{yesterday}T08:00:00Z", "night_date": yesterday,
             "deep_min": None, "light_min": None, "rem_min": None, "awake_min": None},
            {"kind": "sleep", "id": "sleep-dupe", "origin": "com.google", "start": f"{yesterday}T00:30:00Z",
             "end": f"{yesterday}T07:30:00Z", "night_date": yesterday},
            {"kind": "exercise", "id": "auto1", "origin": "com.zepp", "start": f"{yesterday}T12:00:00Z",
             "end": f"{yesterday}T12:30:00Z", "title": "Camminata"},
        ],
    }


def test_idempotent_samples_sessions_and_no_double_workouts(conn):
    packet = sample_data()
    first = health_sync.ingest_payload(conn, packet)
    second = health_sync.ingest_payload(conn, packet)
    assert first["new_hr_samples"] == 2
    assert second["new_hr_samples"] == 0
    assert conn.execute("SELECT COUNT(*) FROM hr_samples").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM hc_events").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM workouts").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM sleeps").fetchone()[0] == 1
    sleep = conn.execute("SELECT * FROM sleeps").fetchone()
    assert sleep["total_min"] == 480 and sleep["light_min"] is None
    daily = conn.execute("SELECT * FROM days").fetchone()
    assert daily["steps"] == 3000 and daily["active_kcal"] == 500
    assert health_sync.status(conn)["stored_sessions"] == 3


def test_hrv_rmssd_is_imported_without_inventing_values(conn):
    packet = sample_data()
    yesterday = packet["days"][0]["date"]
    packet["hrv_rmssd"] = [
        {"ts": f"{yesterday}T05:00:00Z", "night_date": yesterday, "rmssd_ms": 37.5},
        {"ts": f"{yesterday}T06:00:00Z", "night_date": yesterday, "rmssd_ms": 42.0},
    ]
    response = health_sync.ingest_payload(conn, packet)
    assert response["received_hrv"] == 1
    row = conn.execute("SELECT rmssd_ms,source FROM hrv_daily WHERE night_date=?", (yesterday,)).fetchone()
    assert row["rmssd_ms"] == 42.0 and row["source"] == "health_connect"
    assert health_sync.ingest_payload(conn, packet)["received_hrv"] == 1
    assert conn.execute("SELECT COUNT(*) FROM hrv_daily").fetchone()[0] == 1

def test_hrv_from_other_source_is_not_overwritten(conn):
    packet = sample_data()
    yesterday = packet["days"][0]["date"]
    conn.execute("INSERT INTO hrv_daily(night_date,rmssd_ms,source) VALUES(?, ?, 'zepp')", (yesterday, 39.0))
    conn.commit()
    packet["hrv_rmssd"] = [{"night_date": yesterday, "ts": f"{yesterday}T08:00:00Z", "rmssd_ms": 60.0}]
    health_sync.ingest_payload(conn, packet)
    row = conn.execute("SELECT rmssd_ms,source FROM hrv_daily WHERE night_date=?", (yesterday,)).fetchone()
    assert row["rmssd_ms"] == 39.0 and row["source"] == "zepp"

def test_invalid_hrv_aborts_all_writes(conn):
    packet=sample_data()
    yesterday=packet["days"][0]["date"]
    packet["hrv_rmssd"]=[{"night_date":yesterday,"ts":f"{yesterday}T04:00:00Z","rmssd_ms":-5.0}]
    with pytest.raises(ValueError):
        health_sync.ingest_payload(conn, packet)
    assert conn.execute("SELECT COUNT(*) FROM hr_samples").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM hrv_daily").fetchone()[0] == 0

def test_daily_updates_are_replacements_not_sums(conn):
    payload = sample_data()
    health_sync.ingest_payload(conn, payload)
    payload["days"][0]["steps"] = 5000
    payload["days"][0]["active_kcal"] = 650.0
    health_sync.ingest_payload(conn, payload)
    row = conn.execute("SELECT * FROM days").fetchone()
    assert row["steps"] == 5000
    assert row["active_kcal"] == 650.0


def test_hc_owned_steps_update_without_overwriting_zepp_calories(conn):
    packet = sample_data()
    yesterday = packet["days"][0]["date"]
    conn.execute("INSERT INTO days(date,active_kcal,source) VALUES(?,777,'zepp')", (yesterday,))
    conn.commit()
    health_sync.ingest_payload(conn, packet)
    packet["days"][0]["steps"] = 6200
    packet["days"][0]["active_kcal"] = 650.0
    health_sync.ingest_payload(conn, packet)
    row = conn.execute("SELECT * FROM days").fetchone()
    assert row["steps"] == 6200
    assert row["active_kcal"] == 777
    assert row["source"] == "zepp"


def test_existing_zepp_sleep_and_active_kcal_not_clobbered(conn):
    packet = sample_data()
    yesterday = packet["days"][0]["date"]
    conn.execute("INSERT INTO sleeps(night_date,light_min,source) VALUES(?,123,'zepp')", (yesterday,))
    conn.execute("INSERT INTO days(date,active_kcal,source) VALUES(?,777,'zepp')", (yesterday,))
    conn.commit()
    health_sync.ingest_payload(conn, packet)
    assert conn.execute("SELECT light_min FROM sleeps").fetchone()[0] == 123
    assert conn.execute("SELECT active_kcal FROM days").fetchone()[0] == 777


@pytest.mark.parametrize("mutate", [
    lambda p: p["heart_rates"].append({"ts": "2026-10-21T12:00:00", "bpm": 60}),
    lambda p: p["days"].append({"date": "broken", "steps": 2}),
    lambda p: p["sessions"][0].update({"end": "2020-02-02T00:00:00Z"}),
    lambda p: p["days"][0].update({"active_kcal": -1}),
    lambda p: p.update({"schema": 500}),
])
def test_malformed_payload_is_rejected_atomically(conn, mutate):
    packet = sample_data()
    mutate(packet)
    with pytest.raises((ValueError, TypeError)):
        health_sync.ingest_payload(conn, packet)
    assert conn.execute("SELECT COUNT(*) FROM hr_samples").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM hc_events").fetchone()[0] == 0


def test_partial_sleep_without_stages_marked_estimate(conn):
    packet = sample_data()
    packet["sessions"] = packet["sessions"][:1]
    # Repeat with >=1 sleep and score still possible, but approximation must be flagged
    packet["days"][0]["date"] = date.today().isoformat()
    packet["sessions"][0]["night_date"] = date.today().isoformat()
    health_sync.ingest_payload(conn, packet)
    result = readiness.readiness(conn)
    assert "sleep" in result["components"]
    assert any("stimata" in f for f in result["flags"])


def test_http_authorization_and_upload(monkeypatch, tmp_path):
    monkeypatch.setenv("BENESSERE_DB", str(tmp_path / "net.db"))
    server = SyncHTTPServer(("127.0.0.1", 0), "a-long-random-token-1234567890")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def post(secret=None):
            h = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            headers = {"Content-Type": "application/json"}
            if secret is not None:
                headers["Authorization"] = "Bearer " + secret
            h.request("POST", "/api/v1/health-sync", body=json.dumps(sample_data()), headers=headers)
            response = h.getresponse()
            result = response.status, json.loads(response.read())
            h.close()
            return result

        assert post()[0] == 401
        assert post("invalid")[0] == 401
        assert post("a-long-random-token-1234567890")[0] == 200
        assert post("a-long-random-token-1234567890")[1]["new_hr_samples"] == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
