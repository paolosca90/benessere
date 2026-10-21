"""Deterministic health metrics and additional sensor ingest regression tests."""
from datetime import date
import pytest

from benessere import db, health_metrics, health_sync


@pytest.fixture
def conn(tmp_path):
    c=db.connect(tmp_path/"real.db")
    health_sync.initialize(c)
    yield c
    c.close()


def test_empty_data_no_fabricated_values(conn):
    out=health_metrics.snapshot(conn,date(2026,10,21),7)
    assert out["last_heart"] is None
    assert out["sleep_today"] is None
    assert out["today"] is None
    assert out["counts"]["heart_samples"]==0
    assert any("non" in x.lower() for x in health_metrics.observations(out))


def test_real_measurements_and_session_sleep_not_misrepresented(conn):
    packet={"schema":1,"device_id":"phone1",
      "days":[{"date":"2026-10-21","steps":8600,"active_kcal":420.0,"total_kcal":2300.0}],
      "heart_rates":[{"ts":"2026-10-21T10:00:00Z","bpm":68}],
      "sessions":[{"kind":"sleep","id":"night1","origin":"com.zepp","start":"2026-10-20T21:00:00Z",
                   "end":"2026-10-21T05:00:00Z","night_date":"2026-10-21"}],
      "oxygen_saturation":[{"ts":"2026-10-21T06:40:00Z","pct":98.0}],
      "weights":[{"date":"2026-10-21","weight_kg":81.5}]}
    result=health_sync.ingest_payload(conn,packet)
    assert result["received_spo2"]==1
    assert result["received_weights"]==1
    assert health_sync.ingest_payload(conn,packet)["new_hr_samples"]==0
    out=health_metrics.snapshot(conn,"2026-10-21",7)
    assert out["today"]["steps"]==8600
    assert out["today"]["weight_kg"]==81.5
    assert out["last_heart"]["bpm"]==68
    assert out["last_spo2"]["pct"]==98.0
    assert out["sleep_today"]["duration_h"]==8
    assert out["sleep_today"]["accuracy"]=="durata sessione (non sonno effettivo)"
    assert out["hr_hourly"][0]["average_bpm"]==68


def test_invalid_oxygen_rolls_back_everything(conn):
    with pytest.raises(ValueError):
        health_sync.ingest_payload(conn,{"schema":1,"device_id":"phone1",
           "days":[{"date":"2026-10-21","steps":4000}],
           "oxygen_saturation":[{"ts":"2026-10-21T06:00:00Z","pct":300}]})
    assert conn.execute("SELECT COUNT(*) FROM days").fetchone()[0]==0
