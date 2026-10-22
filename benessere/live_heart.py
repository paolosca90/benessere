"""Ephemeral, user-opted-in heart-rate stream from Bluetooth GATT 180D.

Separate from Health Connect historical measurements. No MAC address is sent or
stored. Timestamps are actual sensor-notification receipt times, not forecasts.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
import sqlite3

MAX_RETENTION_MIN = 30
ONLINE_SECONDS = 15


def initialize(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS live_heart_samples (
            device_id TEXT NOT NULL,
            sampled_at TEXT NOT NULL,
            received_at TEXT NOT NULL,
            bpm INTEGER NOT NULL CHECK(bpm BETWEEN 25 AND 240),
            source TEXT NOT NULL DEFAULT 'ble_180d',
            PRIMARY KEY (device_id, sampled_at)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_live_hr_received
        ON live_heart_samples(received_at)
    """)
    conn.commit()


def _utc(raw: str) -> datetime:
    if not isinstance(raw, str) or len(raw) > 40:
        raise ValueError("Timestamp FC live non valido")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Timestamp FC live non valido") from exc
    if value.tzinfo is None:
        raise ValueError("Timestamp FC live senza fuso orario")
    return value.astimezone(timezone.utc)


def ingest(conn: sqlite3.Connection, payload: dict, now: datetime | None = None) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Payload FC live non valido")
    device = payload.get("device_id")
    if not isinstance(device, str) or not re.fullmatch(r"[A-Za-z0-9_-]{6,100}", device):
        raise ValueError("Identificativo dispositivo non valido")
    bpm = payload.get("bpm")
    if type(bpm) is not int or not 25 <= bpm <= 240:
        raise ValueError("BPM non valido")
    if payload.get("source") != "ble_180d":
        raise ValueError("Origine non riconosciuta")
    sampled_at = _utc(payload.get("sampled_at"))
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("Orologio server senza fuso")
    instant = instant.astimezone(timezone.utc)
    # Reject delayed and future samples rather than showing a fabricated "live".
    if abs((instant - sampled_at).total_seconds()) > 120:
        raise ValueError("Campione FC live troppo vecchio o orologio telefono non sincronizzato")
    initialize(conn)
    cutoff = (instant - timedelta(minutes=MAX_RETENTION_MIN)).isoformat()
    with conn:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO live_heart_samples
               (device_id, sampled_at, received_at, bpm, source)
               VALUES (?,?,?,?,?)""",
            (device, sampled_at.isoformat(), instant.isoformat(), bpm, "ble_180d")
        )
        conn.execute("DELETE FROM live_heart_samples WHERE received_at < ?", (cutoff,))
    return {"accepted": bool(cursor.rowcount), "received_at": instant.isoformat()}


def snapshot(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    initialize(conn)
    instant = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    # A live chart has no historical overlap with synced Health Connect records.
    since = (instant - timedelta(minutes=2)).isoformat()
    rows = conn.execute(
        """SELECT sampled_at, received_at, bpm FROM live_heart_samples
           WHERE received_at >= ? ORDER BY received_at DESC LIMIT 180""",
        (since,)
    ).fetchall()
    latest = conn.execute(
        """SELECT sampled_at, received_at, bpm FROM live_heart_samples
           ORDER BY received_at DESC LIMIT 1"""
    ).fetchone()
    age = round((instant - _utc(latest["received_at"])).total_seconds(), 1) if latest else None
    online = age is not None and 0 <= age <= ONLINE_SECONDS
    return {
        "status": "live" if online else "offline",
        "bpm": latest["bpm"] if online else None,
        "last_bpm": latest["bpm"] if latest else None,
        "last_received_at": latest["received_at"] if latest else None,
        "seconds_since_last": age,
        "source": "ble_180d" if latest else None,
        "points": [
            {"at": r["sampled_at"], "bpm": r["bpm"]}
            for r in reversed(rows)
        ] if online else [],
        "expiry_seconds": ONLINE_SECONDS,
    }
