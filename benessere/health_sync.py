"""Ricezione Health Connect: validazione, storage idempotente, nessun doppio conteggio."""
from __future__ import annotations

import math
import sqlite3
from datetime import date, datetime, timezone

MAX_SAMPLES = 50000
MAX_EVENTS = 2500
MAX_DAYS = 8


def _date(s: object) -> str:
    if not isinstance(s, str) or len(s) != 10:
        raise ValueError("data ISO YYYY-MM-DD richiesta")
    return date.fromisoformat(s).isoformat()


def _iso(s: object) -> str:
    if not isinstance(s, str) or len(s) > 40:
        raise ValueError("timestamp ISO richiesto")
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timestamp deve contenere timezone")
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def _id(s: object, name: str = "id") -> str:
    if not isinstance(s, str) or not (1 <= len(s) <= 160) or any(ord(c) < 32 for c in s):
        raise ValueError(f"{name} mancante/non valido")
    return s


def _value(v: object, max_value: float, *, integer: bool = False) -> float | int | None:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or v < 0 or v > max_value:
        raise ValueError("valore numerico fuori intervallo")
    if integer and (not isinstance(v, int) or isinstance(v, bool)):
        raise ValueError("atteso intero")
    return int(v) if integer else float(v)


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS hc_daily (
      date TEXT PRIMARY KEY,
      device_id TEXT NOT NULL,
      steps INTEGER,
      active_kcal REAL,
      total_kcal REAL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS hc_events (
      device_id TEXT NOT NULL,
      kind TEXT NOT NULL CHECK(kind IN ('sleep','exercise')),
      record_id TEXT NOT NULL,
      origin TEXT NOT NULL,
      start_at TEXT NOT NULL,
      end_at TEXT NOT NULL,
      night_date TEXT,
      duration_min REAL,
      title TEXT,
      deep_min INTEGER,
      light_min INTEGER,
      rem_min INTEGER,
      awake_min INTEGER,
      updated_at TEXT NOT NULL,
      PRIMARY KEY(device_id,kind,origin,record_id)
    );
    CREATE TABLE IF NOT EXISTS hc_sync_log (
      id INTEGER PRIMARY KEY CHECK(id=1),
      device_id TEXT,
      synced_at TEXT,
      imported_samples INTEGER,
      imported_events INTEGER
    );
    """)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(sleeps)")}
    if "total_min" not in cols:
        conn.execute("ALTER TABLE sleeps ADD COLUMN total_min INTEGER")
    conn.commit()


def ingest_payload(conn: sqlite3.Connection, payload: object) -> dict:
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise ValueError("schema non supportato")
    device_id = _id(payload.get("device_id"), "device_id")
    day_list = payload.get("days", [])
    hr_list = payload.get("heart_rates", [])
    event_list = payload.get("sessions", [])
    oxygen_list = payload.get("oxygen_saturation", [])
    weight_list = payload.get("weights", [])
    hrv_list = payload.get("hrv_rmssd", [])
    if not isinstance(hrv_list, list) or len(hrv_list) > 2000:
        raise ValueError("troppi campioni HRV")
    if not isinstance(oxygen_list, list) or len(oxygen_list) > 5000:
        raise ValueError("troppi campioni SpO2")
    if not isinstance(weight_list, list) or len(weight_list) > 1000:
        raise ValueError("troppe misure peso")
    if not isinstance(day_list, list) or len(day_list) > MAX_DAYS:
        raise ValueError("numero giorni non valido")
    if not isinstance(hr_list, list) or len(hr_list) > MAX_SAMPLES:
        raise ValueError("troppi campioni FC")
    if not isinstance(event_list, list) or len(event_list) > MAX_EVENTS:
        raise ValueError("troppe sessioni")
    if not day_list and not hr_list and not event_list and not oxygen_list and not weight_list and not hrv_list:
        raise ValueError("payload vuoto")
    updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Validazione completa PRIMA di scrivere. Su errore, rollback di tutto il batch.
    days, heart_rates, sessions, oxygen_samples, weights = [], [], [], [], []
    hrv_latest_by_day = {}
    for measurement in hrv_list:
        if not isinstance(measurement, dict):
            raise ValueError("campione HRV non valido")
        day = _date(measurement.get("night_date"))
        time = _iso(measurement.get("ts"))
        rmssd = _value(measurement.get("rmssd_ms"), 200)
        if rmssd is None or rmssd < 1:
            raise ValueError("HRV RMSSD fuori intervallo")
        if day not in hrv_latest_by_day or time > hrv_latest_by_day[day][0]:
            hrv_latest_by_day[day] = (time, rmssd)
    for measurement in oxygen_list:
        if not isinstance(measurement,dict):
            raise ValueError("campione saturazione non valido")
        pct=_value(measurement.get("pct"),100)
        if pct is None or pct < 1:
            raise ValueError("saturazione fuori intervallo")
        oxygen_samples.append((_iso(measurement.get("ts")),pct))
    for measurement in weight_list:
        if not isinstance(measurement,dict):
            raise ValueError("peso non valido")
        weight=_value(measurement.get("weight_kg"),350)
        if weight is None or weight < 20:
            raise ValueError("peso fuori intervallo")
        weights.append((_date(measurement.get("date")),weight))
    for d in day_list:
        if not isinstance(d, dict):
            raise ValueError("giorno non valido")
        days.append((_date(d.get("date")), _value(d.get("steps"), 300000, integer=True),
                     _value(d.get("active_kcal"), 20000),
                     _value(d.get("total_kcal"), 30000)))
    for h in hr_list:
        if not isinstance(h, dict):
            raise ValueError("campione FC non valido")
        bpm = _value(h.get("bpm"), 260, integer=True)
        if bpm is None or bpm < 25:
            raise ValueError("bpm non validi")
        heart_rates.append((_iso(h.get("ts")), bpm))
    for s in event_list:
        if not isinstance(s, dict):
            raise ValueError("sessione non valida")
        kind = s.get("kind")
        if kind not in ("sleep", "exercise"):
            raise ValueError("tipo sessione non valido")
        start, stop = _iso(s.get("start")), _iso(s.get("end"))
        duration = (datetime.fromisoformat(stop) - datetime.fromisoformat(start)).total_seconds() / 60
        if duration <= 0 or duration > 24 * 60:
            raise ValueError("durata sessione non valida")
        night = _date(s.get("night_date")) if kind == "sleep" else None
        title = str(s.get("title", ""))[:200]
        stages = [_value(s.get(k), 1440, integer=True) for k in ("deep_min", "light_min", "rem_min", "awake_min")]
        sessions.append((device_id, kind, _id(s.get("id")), _id(s.get("origin"), "origin"),
                         start, stop, night, round(duration, 2), title, *stages, updated_at))

    try:
        # Connessione dedicata per request; un'unica transazione per batch.
        conn.execute("BEGIN IMMEDIATE")
        before_hr = conn.total_changes
        for ts, bpm in heart_rates:
            conn.execute("INSERT OR IGNORE INTO hr_samples(ts,bpm,source) VALUES(?,?,'health_connect')", (ts, bpm))
        new_hr = conn.total_changes - before_hr
        for ts, pct in oxygen_samples:
            conn.execute("INSERT OR IGNORE INTO spo2_samples(ts,pct,source) VALUES(?, ?, 'health_connect')",
                         (ts,pct))
        # Se presenti più record RMSSD nello stesso giorno, usiamo il più recente;
        # non stimiamo HRV dai battiti e non cancelliamo eventuali valori Zepp diretti.
        for day, (_, rmssd) in hrv_latest_by_day.items():
            conn.execute("""
                INSERT INTO hrv_daily(night_date,rmssd_ms,source)
                VALUES(?,?,'health_connect')
                ON CONFLICT(night_date) DO UPDATE SET
                  rmssd_ms=excluded.rmssd_ms,source=excluded.source
                WHERE hrv_daily.source='health_connect'
            """, (day,rmssd))
        for date_s, weight in weights:
            conn.execute("""INSERT INTO days(date,weight_kg,source) VALUES(?, ?, 'health_connect')
                ON CONFLICT(date) DO UPDATE SET weight_kg=excluded.weight_kg""",(date_s,weight))
        for date_s, steps, active, total in days:
            previous_hc = conn.execute(
                "SELECT steps,active_kcal,total_kcal FROM hc_daily WHERE date=?", (date_s,)
            ).fetchone()
            previous_day = conn.execute(
                "SELECT steps,active_kcal,total_kcal,source FROM days WHERE date=?", (date_s,)
            ).fetchone()

            def updated(field: str, incoming: float | int | None):
                if incoming is None:
                    return previous_day[field] if previous_day else None
                if not previous_day or previous_day["source"] == "health_connect":
                    return incoming
                if previous_day[field] is None:
                    return incoming
                # Una fonte Zepp già valorizzata resta prioritaria; un valore
                # precedentemente fornito da HC può invece essere aggiornato.
                if previous_hc and previous_day[field] == previous_hc[field]:
                    return incoming
                return previous_day[field]

            day_source = previous_day["source"] if previous_day else "health_connect"
            conn.execute("""
                INSERT INTO days(date,steps,active_kcal,total_kcal,source)
                VALUES(?,?,?,?,?)
                ON CONFLICT(date) DO UPDATE SET steps=excluded.steps,
                  active_kcal=excluded.active_kcal,total_kcal=excluded.total_kcal
            """, (date_s, updated("steps", steps), updated("active_kcal", active),
                  updated("total_kcal", total), day_source))
            conn.execute("""
                INSERT INTO hc_daily(date,device_id,steps,active_kcal,total_kcal,updated_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(date) DO UPDATE SET device_id=excluded.device_id,
                  steps=excluded.steps, active_kcal=excluded.active_kcal,
                  total_kcal=excluded.total_kcal, updated_at=excluded.updated_at
            """, (date_s, device_id, steps, active, total, updated_at))
        before_ev = conn.total_changes
        for sess in sessions:
            conn.execute("""
                INSERT INTO hc_events(device_id,kind,record_id,origin,start_at,end_at,night_date,
                  duration_min,title,deep_min,light_min,rem_min,awake_min,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(device_id,kind,origin,record_id) DO UPDATE SET
                  start_at=excluded.start_at, end_at=excluded.end_at,
                  night_date=excluded.night_date,duration_min=excluded.duration_min,
                  title=excluded.title,deep_min=excluded.deep_min,light_min=excluded.light_min,
                  rem_min=excluded.rem_min,awake_min=excluded.awake_min,updated_at=excluded.updated_at
            """, sess)
        # Scegli una singola sessione di sonno per notte: evita la somma di duplicati Zepp/telefono.
        # Nessuna conversione arbitraria del tempo a letto in "sonno leggero".
        for night in {s[6] for s in sessions if s[1] == "sleep"}:
            best = conn.execute("""
                SELECT * FROM hc_events WHERE kind='sleep' AND night_date=?
                ORDER BY duration_min DESC, end_at DESC LIMIT 1
            """, (night,)).fetchone()
            if best:
                conn.execute("""
                    INSERT INTO sleeps(night_date,start,stop,deep_min,light_min,rem_min,
                      awake_min,source,total_min) VALUES(?,?,?,?,?,?,?,'health_connect',?)
                    ON CONFLICT(night_date) DO UPDATE SET
                      start=excluded.start,stop=excluded.stop,deep_min=excluded.deep_min,
                      light_min=excluded.light_min,rem_min=excluded.rem_min,
                      awake_min=excluded.awake_min,total_min=excluded.total_min
                    WHERE sleeps.source='health_connect'
                """, (night, best["start_at"], best["end_at"], best["deep_min"],
                      best["light_min"], best["rem_min"], best["awake_min"],
                      round(best["duration_min"])))
        conn.execute("""
            INSERT INTO hc_sync_log(id,device_id,synced_at,imported_samples,imported_events)
            VALUES(1,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET device_id=excluded.device_id,
              synced_at=excluded.synced_at,imported_samples=excluded.imported_samples,
              imported_events=excluded.imported_events
        """, (device_id, updated_at, new_hr, len(sessions)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"status": "ok", "new_hr_samples": new_hr, "received_days": len(days),
            "received_sessions": len(sessions), "received_spo2": len(oxygen_samples),
            "received_weights": len(weights), "received_hrv": len(hrv_latest_by_day),
            "synced_at": updated_at}


def status(conn: sqlite3.Connection) -> dict:
    initialize(conn)
    row = conn.execute("SELECT * FROM hc_sync_log WHERE id=1").fetchone()
    sessions = conn.execute("SELECT COUNT(*) FROM hc_events").fetchone()[0]
    return {"last_sync": row["synced_at"] if row else None,
            "last_new_hr": row["imported_samples"] if row else 0,
            "stored_sessions": sessions}
