"""Historical sleep-stage intervals imported from completed Health Connect sessions.

The table is intentionally NOT a source of *live* sleep stages. These events
must never activate an alarm, and device origin is not proof of Helio origin.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import sqlite3
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
KINDS = frozenset({"awake", "light", "deep", "rem", "sleeping", "unknown", "out_of_bed"})
MAX_STAGES_PER_SESSION = 2000


def initialize(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hc_sleep_stages (
            device_id TEXT NOT NULL,
            origin TEXT NOT NULL,
            record_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL,
            stage TEXT NOT NULL CHECK(stage IN
              ('awake','light','deep','rem','sleeping','unknown','out_of_bed')),
            PRIMARY KEY(device_id, origin, record_id, position)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_hc_sleep_stages_session
        ON hc_sleep_stages(device_id, origin, record_id, start_at)
    """)


def _instant(raw: object) -> datetime:
    if not isinstance(raw, str) or len(raw) > 40:
        raise ValueError("Timestamp fase di sonno non valido")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Timestamp fase di sonno non valido") from exc
    if dt.tzinfo is None:
        raise ValueError("La fase del sonno richiede un timestamp con fuso")
    return dt.astimezone(timezone.utc)


def normalize(
    stages: object, start: str, end: str
) -> list[tuple[str, str, str]]:
    if not isinstance(stages, list) or len(stages) > MAX_STAGES_PER_SESSION:
        raise ValueError("Elenco fasi del sonno non valido")
    lower, upper = _instant(start), _instant(end)
    output: list[tuple[str, str, str]] = []
    for item in stages:
        if not isinstance(item, dict):
            raise ValueError("Fase del sonno non valida")
        stage = item.get("stage")
        if not isinstance(stage, str) or stage not in KINDS:
            raise ValueError("Tipo fase del sonno non supportato")
        a, b = _instant(item.get("start")), _instant(item.get("end"))
        if not lower <= a < b <= upper:
            raise ValueError("Fase del sonno fuori dalla sessione")
        output.append((a.isoformat(timespec="milliseconds"),
                       b.isoformat(timespec="milliseconds"), stage))
    output.sort()
    for earlier, later in zip(output, output[1:]):
        if earlier[1] > later[0]:
            raise ValueError("Fasi del sonno sovrapposte")
    return output


def upsert_session_in_transaction(
    conn: sqlite3.Connection, device_id: str, origin: str, record_id: str,
    normalized_stages: list[tuple[str, str, str]]
) -> None:
    """Must run after hc_events upsert in the same transaction."""
    conn.execute(
        "DELETE FROM hc_sleep_stages WHERE device_id=? AND origin=? AND record_id=?",
        (device_id, origin, record_id),
    )
    for position, (start, end, stage) in enumerate(normalized_stages, 1):
        conn.execute(
            "INSERT INTO hc_sleep_stages(device_id,origin,record_id,position,start_at,end_at,stage) "
            "VALUES(?,?,?,?,?,?,?)",
            (device_id, origin, record_id, position, start, end, stage),
        )


def report(conn: sqlite3.Connection, day: str) -> dict:
    """Read completed sleep records; never claim live availability."""
    from datetime import date
    target = date.fromisoformat(day).isoformat()
    from . import health_sync
    health_sync.initialize(conn)
    rows = conn.execute(
        """SELECT e.device_id,e.origin,e.record_id,e.start_at,e.end_at,
                  e.deep_min,e.light_min,e.rem_min,e.awake_min,e.duration_min,
                  (SELECT COUNT(*) FROM hc_sleep_stages s
                   WHERE s.device_id=e.device_id AND s.origin=e.origin AND
                     s.record_id=e.record_id) AS phase_count
           FROM hc_events e
           WHERE e.kind='sleep' AND e.night_date=?
           ORDER BY phase_count DESC,e.duration_min DESC,e.end_at DESC""",
        (target,),
    ).fetchall()
    if not rows:
        return {
            "date": target, "status": "missing", "night_session": None,
            "stages": [], "history_only": True, "live_stage_available": False,
            "strap_alarm_verified": False,
            "message": "Nessuna sessione di sonno sincronizzata per questa notte.",
        }
    session = rows[0]
    intervals = conn.execute(
        """SELECT start_at,end_at,stage FROM hc_sleep_stages
           WHERE device_id=? AND origin=? AND record_id=?
           ORDER BY position""",
        (session["device_id"], session["origin"], session["record_id"]),
    ).fetchall()
    stages = []
    for i in intervals:
        start = _instant(i["start_at"]).astimezone(ROME)
        end = _instant(i["end_at"]).astimezone(ROME)
        stages.append({
            "start": start.isoformat(timespec="seconds"),
            "end": end.isoformat(timespec="seconds"),
            "stage": i["stage"],
        })
    status = "timed_history" if stages else "summary_only"
    return {
        "date": target, "status": status,
        "night_session": {
            "start": _instant(session["start_at"]).astimezone(ROME).isoformat(timespec="seconds"),
            "end": _instant(session["end_at"]).astimezone(ROME).isoformat(timespec="seconds"),
            "origin": session["origin"],
            "record_id": session["record_id"],
            "stage_minutes": {
                kind: session[f"{kind}_min"] for kind in ("deep", "light", "rem", "awake")
            },
            "duration_min": session["duration_min"],
            "source": "health_connect",
        },
        "stages": stages,
        "history_only": True, "live_stage_available": False,
        "strap_alarm_verified": False,
        "message": (
            "Fasi temporizzate storiche disponibili. NON sono dati in diretta per la sveglia."
            if stages else
            "Sono arrivati solo i minuti riepilogativi; mancano gli orari delle singole fasi."
        ),
    }
