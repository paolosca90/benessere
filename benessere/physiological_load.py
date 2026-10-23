"""Read-only physiological workload for logged workouts and day context.

Sources: historical timestamped Health Connect/Zepp imports in SQLite.
Bluetooth live_heart_samples is intentionally NOT used: it is ephemeral (30 min)
and its presence does not imply continuous or historical strap coverage.
These metrics are descriptive, not validated clinical or stress scores.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import math
import sqlite3
import statistics
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")


def _instant(raw: str) -> datetime | None:
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None:
            return None
        return value.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        return None


def _heart_for_day(conn: sqlite3.Connection, day: date) -> list[dict]:
    start_local = datetime.combine(day, datetime.min.time(), tzinfo=ROME)
    end_local = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=ROME)
    start, end = start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
    # SQLite holds legacy timestamps with varying offsets; bound by broad UTC dates
    # then compare parsed instants, never lexicographically compare offsets.
    broad_start = (day - timedelta(days=1)).isoformat()
    broad_end = (day + timedelta(days=1)).isoformat()
    rows = conn.execute(
        "SELECT ts,bpm,source FROM hr_samples "
        "WHERE substr(ts,1,10) BETWEEN ? AND ? ORDER BY ts",
        (broad_start, broad_end)
    ).fetchall()
    points = []
    for row in rows:
        instant = _instant(row["ts"])
        bpm = row["bpm"]
        if instant is None or not isinstance(bpm, int) or not 25 <= bpm <= 240:
            continue
        if start <= instant < end:
            points.append({"at": instant, "bpm": bpm, "source": row["source"]})
    return sorted(points, key=lambda p: p["at"])


def _workout_detail(workout: sqlite3.Row, points: list[dict], day: date) -> dict:
    duration = float(workout["duration_min"])
    clock = workout["start_time"]
    result = {
        "id": workout["id"], "type": workout["type"],
        "duration_min": duration, "start_time": clock,
        "rpe": workout["rpe"],
        "session_rpe_au": round(duration * float(workout["rpe"]), 1)
            if workout["rpe"] is not None else None,
        "hr": {
            "status": "time_missing" if not clock else "unavailable",
            "average_bpm": None, "max_bpm": None, "min_bpm": None,
            "sample_count": 0, "sampled_minutes": 0,
            "minute_bin_coverage_pct": None, "sources": [],
            "series": [], "reason": None,
        },
    }
    try:
        if not clock:
            result["hr"]["reason"] = "Orario di inizio non registrato: impossibile collegare la FC."
            return result
        if duration <= 0 or not math.isfinite(duration) or duration > 360:
            result["hr"]["reason"] = "Durata allenamento non valida."
            return result
        start_local = datetime.combine(day, datetime.strptime(clock, "%H:%M").time(), tzinfo=ROME)
        start = start_local.astimezone(timezone.utc)
        end = start + timedelta(minutes=duration)
    except (TypeError, ValueError, OverflowError):
        result["hr"]["reason"] = "Orario di inizio non valido."
        return result

    samples = [p for p in points if start <= p["at"] < end]
    bins: dict[int, list[int]] = defaultdict(list)
    for item in samples:
        minute = int((item["at"] - start).total_seconds() // 60)
        bins[minute].append(item["bpm"])
    total_bins = max(1, math.ceil(duration))
    covered = len(bins)
    coverage_pct = round(covered * 100 / total_bins, 1)
    observed = [
        {"offset_min": minute, "bpm": round(statistics.fmean(values), 1),
         "samples": len(values)} for minute, values in sorted(bins.items())
    ]
    # Explicit nulls create visible gaps, never a fictitious continuous HR curve.
    series = [
        {"offset_min": minute,
         "bpm": round(statistics.fmean(bins[minute]), 1) if minute in bins else None,
         "samples": len(bins.get(minute, []))}
        for minute in range(total_bins)
    ] if samples else []
    hr = result["hr"]
    hr["sample_count"] = len(samples)
    hr["sampled_minutes"] = covered
    hr["minute_bin_coverage_pct"] = coverage_pct
    hr["sources"] = sorted(set(p["source"] for p in samples))
    hr["series"] = series

    if not samples:
        hr["status"] = "unavailable"
        hr["reason"] = "Nessuna FC storica sincronizzata durante l'allenamento."
        return result

    hr["min_bpm"] = min(p["bpm"] for p in samples)
    hr["max_bpm"] = max(p["bpm"] for p in samples)
    # Equal weighting of observed one-minute bins avoids over-weighting
    # high-frequency source bursts. It is not a continuous-session mean
    # unless collection is sufficiently complete.
    hr["average_bpm"] = round(statistics.fmean(item["bpm"] for item in observed), 1)
    long_enough = (observed[-1]["offset_min"] - observed[0]["offset_min"] + 1) >= 0.6 * total_bins
    sufficient = covered >= 6 and coverage_pct >= 60 and long_enough
    hr["status"] = "sufficient" if sufficient else "partial"
    hr["reason"] = (
        "FC rilevata in almeno il 60% dei minuti, con campioni distribuiti nella sessione."
        if sufficient else "FC parziale: media dei soli minuti campionati, non dell'intero WOD."
    )
    return result


def _baseline(conn: sqlite3.Connection, column: str, table: str, key: str,
              day: date, days: int = 14) -> dict:
    if (table, column, key) not in {
        ("hrv_daily", "rmssd_ms", "night_date"),
        ("days", "resting_hr", "date"),
        ("sleeps", "total_min", "night_date"),
    }:
        raise ValueError("Baseline non autorizzata")
    start = (day - timedelta(days=days)).isoformat()
    rows = conn.execute(
        f"SELECT {column} AS value FROM {table} WHERE {key} BETWEEN ? AND ? "
        f"AND {column} IS NOT NULL ORDER BY {key}",
        (start, (day - timedelta(days=1)).isoformat())
    ).fetchall()
    vals = [float(r["value"]) for r in rows
            if isinstance(r["value"], (int, float))
            and math.isfinite(float(r["value"])) and float(r["value"]) > 0]
    return {"days": len(vals), "median": round(statistics.median(vals), 1)
            if len(vals) >= 7 else None}


def report(conn: sqlite3.Connection, day: date) -> dict:
    """A day-specific report; no changes to training records or measurements."""
    from . import health_sync
    health_sync.initialize(conn)
    points = _heart_for_day(conn, day)
    rows = conn.execute(
        "SELECT id,date,type,duration_min,start_time,rpe "
        "FROM workouts WHERE date=? ORDER BY id", (day.isoformat(),)
    ).fetchall()
    workouts = [_workout_detail(row, points, day) for row in rows]
    daily = conn.execute(
        "SELECT steps,active_kcal,total_kcal,resting_hr,source "
        "FROM days WHERE date=?", (day.isoformat(),)
    ).fetchone()
    hrv = conn.execute(
        "SELECT rmssd_ms,source FROM hrv_daily WHERE night_date=?",
        (day.isoformat(),)
    ).fetchone()
    sleep = conn.execute(
        "SELECT deep_min,light_min,rem_min,total_min,source "
        "FROM sleeps WHERE night_date=?", (day.isoformat(),)
    ).fetchone()
    stage_min = sum(int(sleep[k] or 0) for k in ("deep_min", "light_min", "rem_min")) if sleep else 0
    sleep_minutes = stage_min or (sleep["total_min"] if sleep else None)

    totals = {
        "session_rpe_au": round(sum(w["session_rpe_au"] for w in workouts
              if w["session_rpe_au"] is not None), 1) if any(
              w["session_rpe_au"] is not None for w in workouts) else None,
        "workout_minutes": round(sum(w["duration_min"] for w in workouts), 1),
        "rpe_sessions": sum(w["session_rpe_au"] is not None for w in workouts),
        "sessions": len(workouts),
    }
    counts = Counter(p["source"] for p in points)
    basal = {
        "hrv": _baseline(conn, "rmssd_ms", "hrv_daily", "night_date", day),
        "resting_hr": _baseline(conn, "resting_hr", "days", "date", day),
    }
    observations = []
    if not points:
        observations.append("Nessuna FC storica ricevuta per questa giornata. Il Bluetooth live non sostituisce lo storico.")
    if any(w["hr"]["status"] != "sufficient" for w in workouts):
        observations.append("Almeno un allenamento non ha FC con copertura sufficiente per un riepilogo attendibile.")
    if hrv is None or hrv["rmssd_ms"] is None:
        observations.append("HRV non disponibile nella notte selezionata.")
    elif basal["hrv"]["median"] is None:
        observations.append("HRV presente, ma servono almeno 7 notti precedenti per un confronto personale.")
    if daily is None or daily["resting_hr"] is None:
        observations.append("Frequenza a riposo giornaliera assente.")
    elif basal["resting_hr"]["median"] is None:
        observations.append("FC a riposo presente, ma baseline inferiore a 7 giorni.")
    if sleep_minutes is None:
        observations.append("Durata del sonno non disponibile.")
    elif not stage_min:
        observations.append("Solo durata della sessione di sonno: non equivale necessariamente a sonno effettivo.")
    sync = health_sync.status(conn)
    return {
        "date": day.isoformat(), "workouts": workouts,
        "training": totals,
        "day": {
            "steps": daily["steps"] if daily else None,
            "active_kcal": daily["active_kcal"] if daily else None,
            "total_kcal": daily["total_kcal"] if daily else None,
            "resting_hr_bpm": daily["resting_hr"] if daily else None,
            "resting_hr_source": daily["source"] if daily and daily["resting_hr"] is not None else None,
            "hrv_rmssd_ms": hrv["rmssd_ms"] if hrv else None,
            "hrv_source": hrv["source"] if hrv else None,
            "sleep_minutes": sleep_minutes,
            "sleep_basis": "sleep_stages" if stage_min else ("session_duration" if sleep_minutes is not None else None),
            "sleep_source": sleep["source"] if sleep else None,
            "historical_hr_samples": len(points),
            "historical_hr_sources": dict(counts),
        },
        "baselines": basal, "sync": sync, "observations": observations,
        "limitations": [
            "I dati Health Connect non dimostrano quale dispositivo abbia rilevato la FC.",
            "La FC durante la forza/CrossFit non descrive da sola lo sforzo muscolare.",
            "session-RPE (durata x RPE) è una misura soggettiva, distinta dal carico cardiaco.",
            "Il riepilogo della giornata non è un punteggio medico di stress o recupero.",
        ],
    }
