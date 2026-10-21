#!/usr/bin/env python3
"""F0 probe — validazione del canale dati Zepp (API non ufficiale).

Scarica tutte le famiglie di dati disponibili dall'account Zepp collegato
all'Helio Strap, le salva in data/raw/f0/ e stampa un report di granularità
per decidere il canale primario del progetto "benessere".

Prerequisito: config.json col token (vedi docs/04-report-dati.md):
    python vendor/zepp-health-cli/zepp_health.py init capture.har

Uso:
    python f0_probe.py [--days 7]
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor" / "zepp-health-cli"))

from zepp_health import (  # noqa: E402
    USER_EVENT_PRESETS,
    ZeppClient,
    _EVENT_PRESETS,
    load_config,
)

OUT_DIR = ROOT / "data" / "raw" / "f0"

# Preset /v2/users/me/events che ci interessano per i quattro pilastri.
EVENT_PRESETS_PROBE = [
    "hrv",            # hrv_sdnn real_data
    "hrv-rmssd",      # HRVRMSSD real_data
    "readiness",      # readiness watch_score (include temperatura+score)
    "daily-health",   # DailyHealth summary (RHR, score giornalieri)
    "body-battery",   # Charge real_data
    "stress",         # Charge stress_data
    "respiratory",    # RespiratoryRate real_data
]

# Segmenti sport da provare in /v1/sport/{sport}/history.json (fallimenti tollerati).
SPORT_SEGMENTS = ["run", "exercise", "strength_training", "tennis"]


def _interval_stats(items: list) -> dict | None:
    """Statistiche sull'intervallo tra campioni a partire dai timestamp."""
    ts: list[float] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        for k in ("timestamp", "testTime", "time", "startTime", "beginTime", "date"):
            v = it.get(k)
            if isinstance(v, (int, float)) and v > 10**9:
                ts.append(v / 1000 if v > 10**12 else v)
                break
    if len(ts) < 3:
        return None
    ts = sorted(set(ts))
    deltas = sorted(b - a for a, b in zip(ts, ts[1:]) if b > a)
    if not deltas:
        return None
    return {
        "campioni": len(ts),
        "intervallo_mediano_s": round(deltas[len(deltas) // 2], 1),
        "p10_s": round(deltas[int(len(deltas) * 0.1)], 1),
        "p90_s": round(deltas[int(len(deltas) * 0.9)], 1),
    }


def _first_item_keys(items: list) -> str:
    for it in items:
        if isinstance(it, dict):
            return ", ".join(list(it.keys())[:15])
    return ""


def _extract_items(res) -> list:
    if isinstance(res, list):
        return res
    if isinstance(res, dict):
        for k in ("items", "data", "list", "summary"):
            v = res.get(k)
            if isinstance(v, list):
                return v
    return []


def build_probes(w: dict) -> list[tuple[str, object]]:
    """(nome, callable) — ogni callable restituisce il JSON grezzo o solleva."""
    probes: list[tuple[str, object]] = [
        ("user_info", lambda c: c.get_user_info()),
        ("sport_load", lambda c: c.sport_load(w["start_date"], w["end_date"])),
        ("vo2_max", lambda c: c.vo2_max(w["start_date"], w["end_date"])),
        ("heart_rate", lambda c: c.heart_rate(w["start_ts"], w["end_ts"], limit=10000)),
        ("weight", lambda c: c.weight_records(w["start_ts"], w["end_ts"], limit=500)),
        ("band_data_sleep", lambda c: c.band_data(w["start_date"], w["end_date"], query_type="detail")),
        ("second_hr_index", lambda c: c.file_info_events("second_heart_rate", "real_data", w["start_ms"], w["end_ms"], limit=50)),
    ]
    for name in EVENT_PRESETS_PROBE:
        et, st = _EVENT_PRESETS[name]
        probes.append((f"events_{name}", lambda c, et=et, st=st: c.events(et, st, w["start_ms"], w["end_ms"], limit=1000)))
    for name, (et, st) in USER_EVENT_PRESETS.items():
        if st is None:
            probes.append((f"user_events_{name}", lambda c, et=et: c.events_user(et, w["start_ms"], w["end_ms"], limit=1000)))
        else:
            probes.append((f"user_events_{name}", lambda c, et=et, st=st: c.events_user(et, w["start_ms"], w["end_ms"], sub_type=st, limit=1000)))
    for sport in SPORT_SEGMENTS:
        probes.append((f"sport_history_{sport}", lambda c, s=sport: c.sport_history(s, w["start_ts"], w["end_ts"], need_sub_data=1)))
    return probes


def main() -> None:
    ap = argparse.ArgumentParser(description="Probe F0 canale dati Zepp")
    ap.add_argument("--days", type=int, default=7, help="giorni di storia da scaricare (default 7)")
    args = ap.parse_args()

    cfg = load_config()
    token = (cfg.get("app_token") or "").strip()
    uid = str(cfg.get("user_id") or "").strip()
    if not token or not uid:
        print(
            "Token Zepp non configurato.\n\n"
            "1) Cattura il traffico dell'app Zepp con un proxy HTTPS (guida: docs/04-report-dati.md)\n"
            "2) python vendor/zepp-health-cli/zepp_health.py init capture.har\n"
            "3) rilancia python f0_probe.py",
            file=sys.stderr,
        )
        sys.exit(2)

    host = (cfg.get("host") or "api-mifit-us3.zepp.com").strip()
    platform = (cfg.get("app_platform") or "ios_phone").strip()
    client = ZeppClient(token, uid, host=host, app_platform=platform)

    now = datetime.now(timezone.utc)
    w = {
        "end_date": now.date(),
        "start_date": now.date() - timedelta(days=args.days - 1),
        "end_ts": int(now.timestamp()),
        "end_ms": int(now.timestamp() * 1000),
    }
    w["start_ts"] = int((now - timedelta(days=args.days)).timestamp())
    w["start_ms"] = w["start_ts"] * 1000

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report: list[dict] = []
    print(f"Probe F0 — finestra {w['start_date']} → {w['end_date']} su {host}\n")

    for name, fn in build_probes(w):
        row: dict = {"probe": name}
        try:
            res = fn(client)
        except Exception as exc:  # endpoint assente/regione sbagliata: tollerato
            row.update(status="ERRORE", dettaglio=f"{type(exc).__name__}: {str(exc)[:140]}")
            report.append(row)
            print(f"  [ERRORE ] {name:<28} {row['dettaglio']}")
            continue
        out_file = OUT_DIR / f"{name}.json"
        out_file.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        items = _extract_items(res)
        note = _interval_stats(items) or {}
        keys = _first_item_keys(items)
        row.update(
            status="OK",
            items=len(items),
            path=str(out_file.relative_to(ROOT)),
            **note,
        )
        if keys:
            row["campi"] = keys
        report.append(row)
        extra = (
            f"intervallo mediano {note.get('intervallo_mediano_s', '?')} s"
            if note
            else f"campi: {keys[:70]}"
        )
        print(f"  [OK     ] {name:<28} {len(items):>6} item — {extra}")

    summary_path = ROOT / "data" / "f0_report.json"
    summary_path.write_text(
        json.dumps(
            {
                "generato": now.isoformat(),
                "host": host,
                "user_id": uid,
                "giorni": args.days,
                "probes": report,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    ok = sum(1 for r in report if r["status"] == "OK")
    print(f"\n{ok}/{len(report)} probe OK — raw in {OUT_DIR} — report: {summary_path}")
    print("Prossimo passo: compila docs/04-report-dati.md con la tabella granularità.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
