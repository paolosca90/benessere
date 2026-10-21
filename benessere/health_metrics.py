"""Serie salute da sorgenti persistenti: nessun fallback o dato simulato."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import sqlite3

from . import health_sync

ROME = ZoneInfo("Europe/Rome")

def _day(value: date | str) -> str:
    return value.isoformat() if isinstance(value, date) else date.fromisoformat(value).isoformat()

def _local(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        # Storicamente Zepp/Health Connect hanno sempre UTC esplicito.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ROME)

def sleep_minutes(row) -> tuple[int | None, str]:
    if row is None:
        return None, "assente"
    stages = sum(row[k] or 0 for k in ("deep_min", "light_min", "rem_min"))
    if stages:
        return int(stages), "fasi"
    # Quando ci sono solo gli orari non conosciamo i minuti realmente dormiti.
    if row["total_min"] is not None:
        return int(row["total_min"]), "durata sessione (non sonno effettivo)"
    return None, "assente"

def snapshot(conn: sqlite3.Connection, day: date | str, days: int = 30) -> dict:
    """Read-only; seleziona tutti i dati già arrivati dai bridge e dal telefono."""
    if not 1 <= days <= 180:
        raise ValueError("days tra 1 e 180")
    end = _day(day)
    start = (date.fromisoformat(end)-timedelta(days=days-1)).isoformat()
    health_sync.initialize(conn)
    daily = [dict(row) for row in conn.execute(
        "SELECT date,steps,active_kcal,total_kcal,resting_hr,weight_kg,source "
        "FROM days WHERE date BETWEEN ? AND ? ORDER BY date", (start,end)
    ).fetchall()]
    sleeps = []
    for row in conn.execute(
        "SELECT night_date,deep_min,light_min,rem_min,awake_min,total_min,score,source "
        "FROM sleeps WHERE night_date BETWEEN ? AND ? ORDER BY night_date", (start,end)
    ).fetchall():
        minutes, accuracy = sleep_minutes(row)
        sleeps.append({"date":row["night_date"],"duration_min":minutes,
                       "duration_h":round(minutes/60,2) if minutes is not None else None,
                       "accuracy":accuracy,"deep_min":row["deep_min"],
                       "light_min":row["light_min"],"rem_min":row["rem_min"],
                       "awake_min":row["awake_min"],"score":row["score"],"source":row["source"]})
    hrv = [dict(row) for row in conn.execute(
        "SELECT night_date AS date,rmssd_ms,sdnn_ms,source FROM hrv_daily "
        "WHERE night_date BETWEEN ? AND ? ORDER BY night_date", (start,end)
    ).fetchall()]
    # timezone: query UTC day +/- 1 and filter in local timezone.
    from_utc = (date.fromisoformat(start)-timedelta(days=1)).isoformat()
    to_utc = (date.fromisoformat(end)+timedelta(days=1)).isoformat()
    hr_rows = conn.execute(
        "SELECT ts,bpm,source FROM hr_samples WHERE substr(ts,1,10) BETWEEN ? AND ? ORDER BY ts",
        (from_utc,to_utc)
    ).fetchall()
    hr_hourly = defaultdict(list)
    last_hr = None
    hour_counts = defaultdict(int)
    for hr in hr_rows:
        try:
            dt = _local(hr["ts"])
        except (ValueError,TypeError):
            continue
        if not start <= dt.date().isoformat() <= end:
            continue
        local_day=dt.date().isoformat()
        hour_key=f"{local_day} {dt:%H}:00"
        hr_hourly[hour_key].append(hr["bpm"])
        hour_counts[local_day]+=1
        if last_hr is None or dt > last_hr[0]:
            last_hr=(dt, hr["bpm"],hr["source"])
    samples=[{"at":key, "average_bpm":round(sum(v)/len(v),1),
              "min_bpm":min(v),"max_bpm":max(v),"samples":len(v)} for key,v in sorted(hr_hourly.items())]
    oxygen = conn.execute(
        "SELECT ts,pct,source FROM spo2_samples "
        "WHERE substr(ts,1,10) BETWEEN ? AND ? ORDER BY ts DESC LIMIT 1",
        (from_utc,to_utc)
    ).fetchone()
    last_spo2=None
    if oxygen:
        try:
            oxygen_date=_local(oxygen["ts"]).date().isoformat()
            if start <= oxygen_date <= end:
                last_spo2={"pct":oxygen["pct"],"ts":oxygen["ts"],"source":oxygen["source"]}
        except (ValueError,TypeError):pass
    sync=health_sync.status(conn)
    activity_today=next((d for d in reversed(daily) if d["date"]==end),None)
    sleep_today=next((d for d in reversed(sleeps) if d["date"]==end),None)
    hrv_today=next((d for d in reversed(hrv) if d["date"]==end),None)
    return {
        "day":end,"start":start,"daily":daily,"sleeps":sleeps,"hrv":hrv,
        "hr_hourly":samples,"heart_days":dict(hour_counts),
        "last_heart":{"bpm":last_hr[1],"at":last_hr[0].isoformat(),"source":last_hr[2]} if last_hr else None,
        "last_spo2":last_spo2,
        "today":activity_today,"sleep_today":sleep_today,"hrv_today":hrv_today,
        "sync":sync,
        "counts":{"days":len(daily),"sleep_nights":len(sleeps),"hrv_nights":len(hrv),
                  "heart_samples":sum(hour_counts.values())}
    }

def observations(snapshot_data:dict) -> list[str]:
    """Osservazioni contestuali non cliniche e senza soglie diagnostiche arbitrarie."""
    result=[]
    counts=snapshot_data["counts"]
    if not snapshot_data["sync"]["last_sync"]:
        result.append("Il telefono non ha ancora confermato una sincronizzazione Health Connect verso questo database.")
    if not counts["heart_samples"]:
        result.append("Non ci sono campioni di frequenza cardiaca nell'intervallo selezionato.")
    if not counts["sleep_nights"]:
        result.append("Non ci sono sessioni di sonno nell'intervallo selezionato.")
    if not counts["hrv_nights"]:
        result.append("HRV non disponibile: l'app Android attuale non la invia dal telefono; può arrivare da una sorgente Zepp autorizzata.")
    sleeps=[s["duration_h"] for s in snapshot_data["sleeps"] if s["duration_h"] is not None and s["accuracy"]=="fasi"]
    if len(sleeps)>=5:
        avg=sum(sleeps[-7:])/len(sleeps[-7:])
        result.append(f"Sonno con fasi rilevate: media delle ultime {min(7,len(sleeps))} notti disponibili {avg:.1f} h. Non è una diagnosi.")
    if snapshot_data["sleep_today"] and snapshot_data["sleep_today"]["accuracy"]!="fasi":
        result.append("Ultima notte: solo durata della sessione a letto; non viene presentata come sonno effettivo.")
    if not result:
        result.append("Dati disponibili. Confronta più giorni nelle stesse condizioni; per decisioni mediche serve una valutazione professionale.")
    return result
