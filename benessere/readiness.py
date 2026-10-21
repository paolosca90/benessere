"""Readiness: score 0-100 dai dati disponibili (HRV, RHR, sonno, temperatura, carico).

Se i dati Zepp non sono ancora sincronizzati ritorna None con motivazione —
l'app resta pienamente usabile con log manuale.
"""

from __future__ import annotations

import sqlite3
import statistics
from datetime import date, timedelta


def _zscore_vs_baseline(values: list[float], current: float) -> float | None:
    """z-score contro baseline 30 gg; richiede ≥7 giorni di storia."""
    if len(values) < 7:
        return None
    mean = statistics.fmean(values)
    stdev = statistics.pstdev(values)
    if stdev == 0:
        return 0.0
    return (current - mean) / stdev


def readiness(conn: sqlite3.Connection, day: date | None = None) -> dict | None:
    day = day or date.today()
    day_s = day.isoformat()
    window_start = (day - timedelta(days=30)).isoformat()

    components: dict[str, float | None] = {}
    flags: list[str] = []

    # HRV notturna: z-score del giorno vs baseline
    hrv_rows = conn.execute(
        "SELECT rmssd_ms FROM hrv_daily WHERE night_date >= ? AND night_date <= ? AND rmssd_ms IS NOT NULL ORDER BY night_date",
        (window_start, day_s),
    ).fetchall()
    hrv_vals = [r["rmssd_ms"] for r in hrv_rows if r["rmssd_ms"]]
    if hrv_vals:
        z = _zscore_vs_baseline(hrv_vals[:-1], hrv_vals[-1])
        if z is not None:
            components["hrv"] = max(0.0, min(100.0, 50 + 50 * max(min(z, 2), -2) / 2))
        else:
            flags.append("HRV in baseline troppo breve (servono ≥7 notti)")
    else:
        flags.append("HRV non disponibile (sync Zepp o inserimento manuale)")

    # RHR: deviazione dalla baseline
    rhr_rows = conn.execute(
        "SELECT resting_hr FROM days WHERE date >= ? AND date <= ? AND resting_hr IS NOT NULL ORDER BY date",
        (window_start, day_s),
    ).fetchall()
    rhr_vals = [float(r["resting_hr"]) for r in rhr_rows]
    if rhr_vals:
        z = _zscore_vs_baseline(rhr_vals[:-1], rhr_vals[-1])
        if z is not None:
            components["rhr"] = max(0.0, min(100.0, 50 - 50 * max(min(z, 2), -2) / 2))
        else:
            flags.append("RHR baseline breve")
    else:
        flags.append("RHR non disponibile")

    # Sonno: durata vs bisogno personale (default 7.5h, profilo sleep_need_h)
    sleep = conn.execute("SELECT * FROM sleeps WHERE night_date = ?", (day_s,)).fetchone()
    from . import db as store

    need_min = (store.profile_get_float(conn, "sleep_need_h", 7.5) or 7.5) * 60
    if sleep:
        total = (sleep["deep_min"] or 0) + (sleep["light_min"] or 0) + (sleep["rem_min"] or 0)
        if total > 0:
            dur_score = max(0.0, min(100.0, 100 * total / need_min))
            components["sleep"] = dur_score
            debt_rows = conn.execute(
                "SELECT COALESCE(SUM(deep_min + light_min + rem_min),0) AS t FROM sleeps WHERE night_date > ?",
                ((day - timedelta(days=7)).isoformat(),),
            ).fetchone()
            week_total = debt_rows["t"] or 0
            if week_total < need_min * 7 * 0.9:
                flags.append(f"Debito sonno 7 gg: {(need_min * 7 - week_total) / 60:.1f} h sotto fabbisogno")
    else:
        flags.append("Sonno di ieri non registrato")

    # Temperatura: penalità se deviazione marcata (>= +0.5°C)
    temp = conn.execute("SELECT deviation FROM temp_daily WHERE night_date = ?", (day_s,)).fetchone()
    if temp and temp["deviation"] is not None:
        components["temp"] = 100.0 if abs(temp["deviation"]) < 0.5 else 40.0
        if abs(temp["deviation"]) >= 0.5:
            flags.append("Temperatura cutanea fuori baseline (possibile incombenza)")

    # Carico: TSB di ieri clampato
    from . import workouts

    ff = workouts.fitness_fatigue(conn, day, horizon=7)
    if any(x["load"] for x in ff):
        tsb = ff[-1]["tsb"]
        components["load"] = max(0.0, min(100.0, 50 + max(min(tsb, 20), -20) * 2.5))
    else:
        flags.append("Nessun carico allenamenti registrato")

    weights = {"hrv": 0.35, "rhr": 0.20, "sleep": 0.25, "temp": 0.10, "load": 0.10}
    available = {k: v for k, v in components.items() if v is not None}
    if not available:
        return {"date": day_s, "score": None, "components": {}, "flags": flags}

    total_w = sum(weights[k] for k in available)
    score = sum(available[k] * weights[k] for k in available) / total_w
    return {"date": day_s, "score": round(score), "components": {k: round(v) for k, v in available.items()}, "flags": flags}
