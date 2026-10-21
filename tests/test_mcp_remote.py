"""Remote MCP smoke: limited tool exposure, bounded reads and real DB summaries."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import mcp_remote
from benessere import db, health_sync


def test_remote_tool_surface_has_no_export_or_zepp_sync():
    names = set(mcp_remote.mcp._tool_manager._tools)
    assert {"log_meal", "log_workout", "get_health_overview", "get_readiness", "today_snapshot"} <= names
    assert "export_all" not in names
    assert "sync_zepp" not in names


def test_health_overview_reads_existing_rows(monkeypatch, tmp_path: Path):
    path = tmp_path / "health.db"
    conn = db.connect(path)
    health_sync.initialize(conn)
    today = date.today().isoformat()
    conn.execute("INSERT INTO days(date,steps,active_kcal,source) VALUES(?,?,?,'health_connect')",
                 (today, 5432, 340))
    conn.execute("INSERT INTO hr_samples(ts,bpm,source) VALUES(?,?,'health_connect')",
                 (today + "T13:14:15+00:00", 76))
    conn.commit()
    conn.close()
    original_connect = db.connect
    monkeypatch.setattr(mcp_remote.db, "connect", lambda: original_connect(path))
    result = json.loads(mcp_remote.get_health_overview(7))
    assert result["daily"][0]["steps"] == 5432
    assert result["heart_rate_by_utc_date"][0]["avg_bpm"] == 76
    assert result["sync_status"]["stored_sessions"] == 0


@pytest.mark.parametrize("value", [-1, 0, 31, 10000])
def test_health_overview_rejects_invalid_period(value):
    with pytest.raises(ValueError):
        mcp_remote.get_health_overview(value)


def test_meal_rejects_invalid_data_without_writing():
    with pytest.raises(ValueError):
        mcp_remote.log_meal("lunch", float("nan"), 10, 10, 10)
    with pytest.raises(ValueError):
        mcp_remote.log_meal("invalid", 500, 10, 10, 10)


def test_workout_requires_actual_duration():
    with pytest.raises(ValueError):
        mcp_remote.log_workout(date.today().isoformat(), "metcon", 0)
