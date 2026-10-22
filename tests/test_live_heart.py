"""FC Bluetooth 180D in tempo reale: consenso, freschezza e autorizzazione."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from benessere import db, live_heart
from sync_server import SyncHTTPServer
from webapp.api.main import app


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test_live.sqlite3")
    live_heart.initialize(connection)
    yield connection
    connection.close()


def _payload(now, bpm=72, **updates):
    data = {
        "device_id": "android_canary_1234",
        "sampled_at": now.isoformat(),
        "bpm": bpm,
        "source": "ble_180d",
    }
    data.update(updates)
    return data


def test_initially_offline_and_no_fabricated_bpm(conn):
    before = live_heart.snapshot(conn)
    assert before["status"] == "offline"
    assert before["bpm"] is None
    assert before["last_bpm"] is None
    assert before["points"] == []


def test_fresh_live_then_expires(conn):
    now = datetime(2026, 10, 22, 14, 21, tzinfo=timezone.utc)
    assert live_heart.ingest(conn, _payload(now, bpm=69), now)["accepted"]
    next_at = now + timedelta(seconds=3)
    assert live_heart.ingest(conn, _payload(next_at, bpm=72), next_at)["accepted"]
    live = live_heart.snapshot(conn, next_at + timedelta(seconds=4))
    assert live["status"] == "live"
    assert live["bpm"] == 72
    assert [p["bpm"] for p in live["points"]] == [69, 72]
    after = live_heart.snapshot(conn, next_at + timedelta(seconds=17))
    assert after["status"] == "offline"
    assert after["bpm"] is None
    assert after["last_bpm"] == 72
    assert after["points"] == []


def test_duplicate_ignored_and_aged_samples_rejected(conn):
    now = datetime(2026, 10, 22, 14, 21, tzinfo=timezone.utc)
    packet = _payload(now)
    assert live_heart.ingest(conn, packet, now)["accepted"]
    assert not live_heart.ingest(conn, packet, now)["accepted"]
    assert conn.execute("SELECT COUNT(*) FROM live_heart_samples").fetchone()[0] == 1
    with pytest.raises(ValueError, match="troppo vecchio"):
        live_heart.ingest(conn, _payload(now - timedelta(minutes=4)), now)
    with pytest.raises(ValueError, match="troppo vecchio"):
        live_heart.ingest(conn, _payload(now + timedelta(minutes=4)), now)


@pytest.mark.parametrize("wrong", [
    {"bpm": 260}, {"bpm": 0}, {"bpm": 72.5},
    {"device_id": "x"},
    {"source": "health_connect"},
    {"sampled_at": "2026-10-22T14:21:00"},
    {"sampled_at": "not-a-timestamp"},
])
def test_reject_invalid_sensor_samples(conn, wrong):
    now = datetime(2026, 10, 22, 14, 21, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        live_heart.ingest(conn, _payload(now, **wrong), now)
    assert conn.execute("SELECT COUNT(*) FROM live_heart_samples").fetchone()[0] == 0


def test_retention_window(conn):
    now = datetime(2026, 10, 22, 14, 21, tzinfo=timezone.utc)
    for i in (31, 25, 15, 0):
        stamp = now - timedelta(minutes=i)
        live_heart.ingest(conn, _payload(stamp, bpm=70+i), stamp)
    live_heart.ingest(conn, _payload(now + timedelta(seconds=1)), now + timedelta(seconds=1))
    assert conn.execute("SELECT COUNT(*) FROM live_heart_samples").fetchone()[0] == 4
    assert live_heart.snapshot(conn, now + timedelta(seconds=2))["bpm"] == 72


def test_dashboard_endpoint_authorized(tmp_path, monkeypatch):
    path = tmp_path / "api.sqlite3"
    monkeypatch.setenv("BENESSERE_DB", str(path))
    secret = "A" * 45
    monkeypatch.setenv("BENESSERE_WEB_API_TOKEN", secret)
    with TestClient(app) as client:
        assert client.get("/v1/live-heart-rate").status_code == 401
        r = client.get("/v1/live-heart-rate", headers={"Authorization": f"Bearer {secret}"})
        assert r.status_code == 200
        assert r.json()["status"] == "offline"


def test_android_ingest_authorized_without_touching_hc(tmp_path, monkeypatch):
    import json, threading
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
    path = tmp_path / "android.sqlite3"
    monkeypatch.setenv("BENESSERE_DB", str(path))
    token = "ANDROID_SYNC_SECRET" + "x" * 24
    server = SyncHTTPServer(("127.0.0.1", 0), token)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/api/v1/live-heart-rate"
        sample = _payload(datetime.now(timezone.utc), bpm=73)
        data = json.dumps(sample).encode()
        bad = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(HTTPError) as denied:
            urlopen(bad, timeout=3)
        assert denied.value.code == 401
        req = Request(url, data=data, headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        }, method="POST")
        with urlopen(req, timeout=4) as answer:
            assert answer.status == 200
            assert json.load(answer)["accepted"] is True
        with db.connect(path) as database:
            assert database.execute("SELECT COUNT(*) FROM live_heart_samples").fetchone()[0] == 1
            assert database.execute("SELECT COUNT(*) FROM hr_samples").fetchone()[0] == 0
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
