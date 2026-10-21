"""Server MCP di Benessere — collega i tuoi dati ai client MCP (ChatGPT, Claude, …).

Modalità:
  python mcp_server.py              → stdio   (Claude Desktop / Claude Code)
  python mcp_server.py --http 8000  → streamable HTTP su http://localhost:8000/mcp
                                      (ChatGPT: Impostazioni → Connettori → server MCP)

Guida completa: docs/07-mcp-chatgpt.md
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime

from benessere import db as store
from benessere import ingest, nutrition, readiness, reminders, seed_wods, workouts, wods

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("benessere")


def _conn():
    return store.connect()


def _d(day: str | None) -> str:
    return day or date.today().isoformat()


# ---------- Snapshot e stato ----------

@mcp.tool()
def today_snapshot() -> str:
    """Panoramica di oggi: readiness, target nutrizionali, pasti registrati, reminder attivi."""
    conn = _conn()
    try:
        day_s = date.today().isoformat()
        plan = nutrition.compute_targets(conn)
        targets = plan.as_dict() if plan else None
        eaten = nutrition.day_totals(conn, day_s)
        rem = reminders.pending_meal_reminders(conn)
        ff = workouts.fitness_fatigue(conn, horizon=7)[-1]
        return json.dumps(
            {
                "date": day_s,
                "readiness": readiness.readiness(conn),
                "targets": targets,
                "eaten": eaten,
                "remaining": {
                    "kcal": round(targets["target_kcal"] - eaten["kcal"]) if targets else None,
                    "protein_g": round(targets["protein_g"] - eaten["protein_g"]) if targets else None,
                },
                "meal_reminders": rem,
                "training_load": {"ctl": ff["ctl"], "atl": ff["atl"], "tsb": ff["tsb"]},
            },
            ensure_ascii=False,
            indent=2,
        )
    finally:
        conn.close()


@mcp.tool()
def get_readiness(days: int = 14) -> str:
    """Storico readiness (0-100) con componenti e flag degli ultimi N giorni."""
    conn = _conn()
    try:
        out = []
        for i in range(days - 1, -1, -1):
            r = readiness.readiness(conn, date.today() - __import__("datetime").timedelta(days=i))
            if r:
                out.append(r)
        return json.dumps(out, ensure_ascii=False, indent=2)
    finally:
        conn.close()


# ---------- Allenamenti ----------

@mcp.tool()
def get_workouts(days: int = 30) -> str:
    """Sessioni di allenamento degli ultimi N giorni con carico calcolato."""
    conn = _conn()
    try:
        start = (date.today() - __import__("datetime").timedelta(days=days - 1)).isoformat()
        rows = workouts.workouts_between(conn, start, date.today().isoformat())
        return json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2)
    finally:
        conn.close()


@mcp.tool()
def log_workout(date: str, type: str, duration_min: float, rpe: float = None, avg_hr: int = None, notes: str = "") -> str:
    """Registra una sessione. type: strength|metcon|gymnastics|skill|tennis|other. rpe 1-10.

    FLUSSO FOTO: da una foto della lavagnetta/WOD svolto ricava type (metcon se
    circuito ad alta intensità, strength se lavoro di forza/sollevamenti,
    gymnastics se bodyweight/skills), durata stimata e RPE se dichiarato;
    metti il WOD trascritto in notes.
    """
    conn = _conn()
    try:
        wid = workouts.add_workout(
            conn,
            workouts.Workout(date=date, type=type, duration_min=duration_min, rpe=rpe, avg_hr=avg_hr, notes=notes, source="mcp"),
        )
        return json.dumps({"id": wid, "status": "registrato"}, ensure_ascii=False)
    finally:
        conn.close()


@mcp.tool()
def get_training_load(days: int = 30) -> str:
    """Fitness (CTL), fatica (ATL) e forma (TSB) giorno per giorno."""
    conn = _conn()
    try:
        return json.dumps(workouts.fitness_fatigue(conn, horizon=days), ensure_ascii=False, indent=2)
    finally:
        conn.close()


# ---------- WOD ----------

@mcp.tool()
def list_wods() -> str:
    """Catalogo WOD (benchmark + custom) con tipo di punteggio."""
    conn = _conn()
    try:
        return json.dumps([dict(r) for r in wods.list_wods(conn)], ensure_ascii=False, indent=2)
    finally:
        conn.close()


@mcp.tool()
def add_wod(name: str, score_type: str, description: str = "", category: str = "custom") -> str:
    """Crea un WOD custom. score_type: time|amrap|load|reps.

    FLUSSO FOTO: se l'utente allega la foto della lavagnetta del box, trascrivi
    il WOD (nome se presente, movimenti, ripetizioni, carichi, time-cap) in
    description e crea il WOD con lo score_type corretto (amrap se "AMRAP x'",
    time se "for time", load per massimali).
    """
    conn = _conn()
    try:
        wid = wods.add_wod(conn, wods.Wod(name=name, score_type=score_type, category=category, description=description, custom=1))
        return json.dumps({"id": wid, "name": name, "score_type": score_type}, ensure_ascii=False)
    finally:
        conn.close()


@mcp.tool()
def log_wod_result(wod: str, date: str, score: str, scaling: str = "rx", notes: str = "") -> str:
    """Registra un risultato. score: tempo "3:45", amrap "12+35", load "142.5", reps "87"."""
    conn = _conn()
    try:
        res = wods.add_result(conn, wod, date, score, scaling=scaling, notes=notes)
        return json.dumps(res, ensure_ascii=False)
    finally:
        conn.close()


@mcp.tool()
def get_wod_history(wod: str) -> str:
    """Storico risultati di un WOD."""
    conn = _conn()
    try:
        rows = wods.results_for(conn, wod)
        return json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2)
    finally:
        conn.close()


@mcp.tool()
def get_prs() -> str:
    """Personali best (PR) per ogni WOD e scaling."""
    conn = _conn()
    try:
        return json.dumps(wods.prs(conn), ensure_ascii=False, indent=2)
    finally:
        conn.close()


# ---------- Alimentazione ----------

@mcp.tool()
def get_nutrition(date: str = None) -> str:
    """Target vs mangiato in una giornata (default: oggi) + reminder pasti mancanti."""
    conn = _conn()
    try:
        day_s = _d(date)
        plan = nutrition.compute_targets(conn, __import__("datetime").date.fromisoformat(day_s))
        targets = plan.as_dict() if plan else None
        eaten = nutrition.day_totals(conn, day_s)
        return json.dumps(
            {
                "date": day_s,
                "targets": targets,
                "eaten": eaten,
                "reminders": reminders.pending_meal_reminders(conn),
            },
            ensure_ascii=False,
            indent=2,
        )
    finally:
        conn.close()


@mcp.tool()
def log_meal(meal: str, kcal: float = 0, protein_g: float = 0, carbs_g: float = 0, fat_g: float = 0, description: str = "") -> str:
    """Registra un pasto. meal: breakfast|lunch|dinner|snack.

    FLUSSO FOTO: se l'utente allega la foto di un pasto, descrivi ciò che vedi,
    STIMA kcal e macro con la tua conoscenza nutritionale, poi chiama questo tool
    con i valori stimati e description = elenco dei cibi.
    """
    conn = _conn()
    try:
        ts = nutrition.log_meal(conn, meal, kcal, protein_g, carbs_g, fat_g, description)
        return json.dumps({"ts": ts, "meal": meal, "status": "registrato"}, ensure_ascii=False)
    finally:
        conn.close()


# ---------- Sincronizzazione device ----------

@mcp.tool()
def set_profile(weight_kg: float = None, goal: str = None, resting_hr: int = None, sleep_need_h: float = None) -> str:
    """Aggiorna il profilo (peso corporeo, obiettivo cut|maintain|bulk, FC riposo, ore di sonno necessarie).

    FLUSSO FOTO: da una foto della bilancia, leggi il peso e chiama questo tool.
    """
    conn = _conn()
    try:
        updates = {
            "weight_kg": weight_kg,
            "goal": goal,
            "resting_hr": resting_hr,
            "sleep_need_h": sleep_need_h,
        }
        changed = {}
        for k, v in updates.items():
            if v is not None:
                store.profile_set(conn, k, v)
                changed[k] = v
        return json.dumps({"status": "profilo aggiornato", "changed": changed}, ensure_ascii=False)
    finally:
        conn.close()

@mcp.tool()
def sync_zepp(days: int = 7) -> str:
    """Sincronizza i dati dal cloud Zepp (Helio Strap): FC, HRV, sonno, temperatura, carico.

    Richiede il token configurato (docs/04-report-dati.md).
    """
    conn = _conn()
    try:
        return json.dumps(ingest.sync(conn, days), ensure_ascii=False, indent=2)
    except RuntimeError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    finally:
        conn.close()


@mcp.tool()
def export_all() -> str:
    """Dump completo del DB (per analisi esterne)."""
    conn = _conn()
    try:
        dump = {}
        for table in (
            "profile", "workouts", "wods", "wod_results", "meals",
            "days", "sleeps", "hrv_daily", "temp_daily", "hr_samples",
        ):
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            dump[table] = [dict(r) for r in rows]
        return json.dumps(dump, ensure_ascii=False, default=str)
    finally:
        conn.close()


def bearer_auth_middleware(token: str):
    """401 su ogni richiesta senza header Authorization: Bearer <token>."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    class BearerAuth(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.headers.get("authorization") != f"Bearer {token}":
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    return BearerAuth


def main() -> None:
    ap = argparse.ArgumentParser(description="Server MCP di Benessere")
    ap.add_argument("--http", type=int, metavar="PORTA", help="avvia in modalità streamable HTTP su /mcp")
    args = ap.parse_args()

    # garantisce schema + seed WOD alla prima connessione di qualunque client
    conn = _conn()
    seed_wods.seed_if_empty(conn)
    conn.close()

    if args.http:
        token = os.environ.get("MCP_TOKEN", "").strip()
        host = os.environ.get("MCP_HOST", "127.0.0.1")
        if token:
            import uvicorn

            app = mcp.streamable_http_app()
            app.add_middleware(bearer_auth_middleware(token))
            uvicorn.run(app, host=host, port=args.http)
        else:
            mcp.settings.host = host
            mcp.settings.port = args.http
            mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
