"""Ingest dal cloud Zepp (canale primario) con parsing tollerante.

Richiede config.json col token (docs/04). Ogni blocco è indipendente:
se un endpoint cambia forma, gli altri continuano a funzionare e
l'errore viene riportato nella lista issues.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import db as store

VENDOR_CLI = Path(__file__).resolve().parent.parent / "vendor" / "zepp-health-cli"


def _client():
    sys.path.insert(0, str(VENDOR_CLI))
    from zepp_health import (  # noqa: PLC0415
        _EVENT_PRESETS,
        ZeppClient,
        load_config,
    )

    cfg = load_config()
    token = (cfg.get("app_token") or "").strip()
    uid = str(cfg.get("user_id") or "").strip()
    if not token or not uid:
        raise RuntimeError(
            "Token Zepp assente. Segui docs/04-report-dati.md: cattura HAR + "
            "python vendor/zepp-health-cli/zepp_health.py init capture.har"
        )
    client = ZeppClient(
        token,
        uid,
        host=(cfg.get("host") or "api-mifit-us3.zepp.com").strip(),
        app_platform=(cfg.get("app_platform") or "ios_phone").strip(),
    )
    return client, _EVENT_PRESETS


def sync(conn: sqlite3.Connection, days: int = 7) -> dict:
    """Pull incrementale; ritorna {imported: {...}, issues: [...]}."""
    client, presets = _client()
    now = datetime.now(timezone.utc)
    start_date = now.date() - timedelta(days=days - 1)
    start_ts = int((now - timedelta(days=days)).timestamp())
    end_ts = int(now.timestamp())
    imported: dict[str, int] = {}
    issues: list[str] = []

    def guard(name: str, fn):
        try:
            imported[name] = fn()
        except Exception as exc:  # noqa: BLE001 — ogni blocco è indipendente
            issues.append(f"{name}: {type(exc).__name__}: {str(exc)[:120]}")

    # --- Giorni: sport load (training load + calorie) ---
    def do_sport_load() -> int:
        data = client.sport_load(start_date, now.date())
        n = 0
        for it in data.get("items") or []:
            day = it.get("dayId")
            if not day:
                continue
            conn.execute(
                "INSERT INTO days(date, active_kcal, source) VALUES(?,?,'zepp') "
                "ON CONFLICT(date) DO UPDATE SET active_kcal=excluded.active_kcal",
                (day, it.get("calorieSum")),
            )
            n += 1
        conn.commit()
        return n

    guard("sport_load", do_sport_load)

    # --- HR serie (al minuto) ---
    def do_hr() -> int:
        data = client.heart_rate(start_ts, end_ts, limit=20000)
        n = 0
        for it in data.get("items") or []:
            ts = it.get("timestamp")
            bpm = it.get("value", {}).get("hr") if isinstance(it.get("value"), dict) else it.get("hr")
            if ts and bpm:
                ts_s = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(timespec="seconds")
                conn.execute(
                    "INSERT OR REPLACE INTO hr_samples(ts, bpm, source) VALUES(?,?,'zepp')", (ts_s, int(bpm))
                )
                n += 1
        conn.commit()
        return n

    guard("heart_rate", do_hr)

    # --- HRV SDNN e RMSSD ---
    for preset_key, col in (("hrv", "sdnn_ms"), ("hrv-rmssd", "rmssd_ms")):
        et, st = presets[preset_key]

        def do_hrv(et=et, st=st, col=col) -> int:
            data = client.events(et, st, int(start_ts * 1000), int(end_ts * 1000), limit=1000)
            n = 0
            for it in data.get("items") or []:
                ts = it.get("timestamp")
                val = it.get("value")
                if not ts or not isinstance(val, dict):
                    continue
                v = val.get("value") or val.get("sdnn") or val.get("rmssd")
                if v is None:
                    continue
                night = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat()
                conn.execute(
                    f"INSERT INTO hrv_daily(night_date, {col}, source) VALUES(?,?,'zepp') "
                    f"ON CONFLICT(night_date) DO UPDATE SET {col}=excluded.{col}",
                    (night, float(v)),
                )
                n += 1
            conn.commit()
            return n

        guard(f"hrv_{preset_key}", do_hrv)

    # --- Temperatura (readiness watch_score) ---
    def do_temp() -> int:
        et, st = presets["readiness"]
        data = client.events(et, st, int(start_ts * 1000), int(end_ts * 1000), limit=500)
        n = 0
        for it in data.get("items") or []:
            ts = it.get("timestamp")
            val = it.get("value") or {}
            cal = val.get("skinTempCalibrated")
            if ts and cal not in (None, 255):
                night = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat()
                conn.execute(
                    "INSERT INTO temp_daily(night_date, deviation, source) VALUES(?,?,'zepp') "
                    "ON CONFLICT(night_date) DO UPDATE SET deviation=excluded.deviation",
                    (night, cal / 100.0),
                )
                n += 1
        conn.commit()
        return n

    guard("temperature", do_temp)

    # --- Sonno (band_data detail; struttura da confermare con F0) ---
    def do_sleep() -> int:
        data = client.band_data(start_date, now.date(), query_type="detail")
        n = 0
        # struttura nota dalle catture community: {items:[{date_id, data:{sleep:{...}}}]},
        # ma varia: meglio cercare ricorsivamente le chiavi sleep note.
        def walk(node, found):
            if isinstance(node, dict):
                if "sleep" in node and isinstance(node["sleep"], dict):
                    found.append(node["sleep"])
                for v in node.values():
                    walk(v, found)
            elif isinstance(node, list):
                for v in node:
                    walk(v, found)

        found: list[dict] = []
        walk(data, found)
        for s in found:
            start_ms = s.get("startTime") or s.get("start")
            stop_ms = s.get("endTime") or s.get("stop")
            if not start_ms or not stop_ms:
                continue
            night = datetime.fromtimestamp(int(start_ms) / 1000, tz=timezone.utc).date().isoformat()
            stages = s.get("stages") or {}
            conn.execute(
                "INSERT OR REPLACE INTO sleeps(night_date, start, stop, deep_min, light_min, rem_min, awake_min, score, source) "
                "VALUES(?,?,?,?,?,?,?,?, 'zepp')",
                (
                    night,
                    datetime.fromtimestamp(int(start_ms) / 1000, tz=timezone.utc).isoformat(timespec="seconds"),
                    datetime.fromtimestamp(int(stop_ms) / 1000, tz=timezone.utc).isoformat(timespec="seconds"),
                    int(stages.get("deep", 0)),
                    int(stages.get("light", 0)),
                    int(stages.get("rem", 0)),
                    int(stages.get("awake", 0)),
                    s.get("score"),
                ),
            )
            n += 1
        conn.commit()
        return n

    guard("sleep", do_sleep)

    return {"imported": imported, "issues": issues, "days": days, "synced_at": datetime.now().isoformat(timespec="seconds")}


def token_present() -> bool:
    for p in (Path.cwd() / "config.json", Path.home() / ".config" / "zepp" / "config.json"):
        if p.is_file():
            try:
                cfg = json.loads(p.read_text())
                if cfg.get("app_token") and cfg.get("user_id"):
                    return True
            except json.JSONDecodeError:
                pass
    return False
