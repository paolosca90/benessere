"""Configurazione remota della sveglia. Il telefono è l'unico esecutore.

In questa release solo 'fixed': le fasi di sonno e la vibrazione BLE dello
Strap non sono ancora verificate. Le impostazioni web sono PENDING finché
Android non conferma l'installazione nell'AlarmManager.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json
import re
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS alarm_config (
    id INTEGER PRIMARY KEY CHECK(id=1),
    revision INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 0,
    deadline TEXT NOT NULL DEFAULT '07:00',
    window_minutes INTEGER NOT NULL DEFAULT 30,
    weekdays TEXT NOT NULL DEFAULT '[1,2,3,4,5,6,7]',
    mode TEXT NOT NULL DEFAULT 'fixed',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alarm_device_ack (
    device_id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL,
    installed INTEGER NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    received_at TEXT NOT NULL
);
"""

def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _validate_hour(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError("Orario richiesto nel formato HH:MM (24 ore)")
    return value

def validate(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Impostazioni non valide")
    enabled = data.get("enabled", False)
    if type(enabled) is not bool:
        raise ValueError("enabled deve essere booleano")
    deadline = _validate_hour(data.get("deadline", "07:00"))
    window = data.get("window_minutes", 30)
    if type(window) is not int or window not in (15, 30, 45, 60):
        raise ValueError("Finestra ammessa: 15, 30, 45, 60 minuti")
    weekdays = data.get("weekdays", list(range(1, 8)))
    if not isinstance(weekdays, list) or not weekdays or any(type(d) is not int or d not in range(1, 8) for d in weekdays):
        raise ValueError("Giorni non validi: seleziona da lunedì (1) a domenica (7)")
    if len(set(weekdays)) != len(weekdays):
        raise ValueError("Giorni duplicati")
    mode = data.get("mode", "fixed")
    if mode != "fixed":
        raise ValueError("Risveglio per fasi/Helio Strap non ancora collaudato: disponibile solo allarme fisso di sicurezza")
    return {"enabled":enabled,"deadline":deadline,"window_minutes":window,
            "weekdays":sorted(weekdays),"mode":"fixed"}

def read(conn: sqlite3.Connection) -> dict:
    initialize(conn)
    row=conn.execute("SELECT * FROM alarm_config WHERE id=1").fetchone()
    if row is None:
        return {"revision":0,"enabled":False,"deadline":"07:00",
                "window_minutes":30,"weekdays":[1,2,3,4,5,6,7],
                "mode":"fixed","updated_at":None,"delivery":"not_configured",
                "device_ack":None,"strap_control":"not_implemented"}
    data={"revision":row["revision"],"enabled":bool(row["enabled"]),
          "deadline":row["deadline"],"window_minutes":row["window_minutes"],
          "weekdays":json.loads(row["weekdays"]),"mode":row["mode"],
          "updated_at":row["updated_at"],"strap_control":"not_implemented"}
    ack=conn.execute("SELECT revision,installed,error,received_at FROM alarm_device_ack ORDER BY received_at DESC LIMIT 1").fetchone()
    data["device_ack"] = dict(ack) if ack else None
    data["delivery"]="confirmed" if ack and ack["revision"]==row["revision"] and ack["installed"] else (
        "failed" if ack and ack["revision"]==row["revision"] and not ack["installed"] else "pending_phone"
    )
    return data

def save(conn: sqlite3.Connection, data: dict) -> dict:
    clean=validate(data)
    initialize(conn)
    old=read(conn)
    if old["revision"] and all(clean[key]==old[key] for key in clean):
        return old
    with conn:
        conn.execute(
            """INSERT INTO alarm_config
            (id,revision,enabled,deadline,window_minutes,weekdays,mode,updated_at)
            VALUES(1,1,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
            revision=alarm_config.revision+1,
            enabled=excluded.enabled,deadline=excluded.deadline,
            window_minutes=excluded.window_minutes,
            weekdays=excluded.weekdays,mode=excluded.mode,updated_at=excluded.updated_at""",
            (int(clean["enabled"]),clean["deadline"],clean["window_minutes"],
             json.dumps(clean["weekdays"]),clean["mode"],_now())
        )
    return read(conn)

def acknowledge(conn: sqlite3.Connection, device_id: str, revision: int,
                installed: bool, error: str = "") -> dict:
    if not isinstance(device_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{6,100}",device_id):
        raise ValueError("Identificativo dispositivo non valido")
    if type(revision) is not int or revision < 0 or type(installed) is not bool:
        raise ValueError("Conferma dispositivo non valida")
    if not isinstance(error,str) or len(error)>200:
        raise ValueError("Errore troppo lungo")
    initialize(conn)
    actual=read(conn)
    if actual["revision"] != revision:
        raise ValueError("Revisione superata: sincronizza di nuovo")
    with conn:
        conn.execute(
          """INSERT INTO alarm_device_ack(device_id,revision,installed,error,received_at)
             VALUES(?,?,?,?,?) ON CONFLICT(device_id) DO UPDATE SET
             revision=excluded.revision,installed=excluded.installed,
             error=excluded.error,received_at=excluded.received_at""",
          (device_id,revision,int(installed),error,_now())
        )
    return read(conn)
