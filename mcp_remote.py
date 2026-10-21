"""MCP remoto Benessere: superficie ridotta, Bearer obbligatorio, risorse limitate.

Questa API è per client MCP autorizzati, non è una pagina web.
Per ChatGPT un collegamento compatibile può richiedere OAuth e permessi del piano.
"""
from __future__ import annotations

import hmac
import json
import os
from datetime import date, timedelta
from pathlib import Path

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from benessere import db, health_sync
import mcp_server as local

mcp = FastMCP("Benessere - dati e diario personale")


def _token() -> str:
    path = os.environ.get("MCP_TOKEN_FILE")
    token = Path(path).read_text(encoding="utf-8").strip() if path else os.environ.get("MCP_TOKEN", "").strip()
    if len(token) < 32:
        raise RuntimeError("MCP_TOKEN_FILE / MCP_TOKEN mancante o troppo breve")
    return token


class RequireBearer(BaseHTTPMiddleware):
    def __init__(self, app, *, token: str):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request, call_next):
        provided = request.headers.get("authorization", "")
        if not hmac.compare_digest(provided, "Bearer " + self.token):
            return JSONResponse({"error": "unauthorized"}, status_code=401,
                                headers={"Cache-Control": "no-store"})
        return await call_next(request)


def _days(value: int, max_days: int = 30) -> int:
    if not 1 <= value <= max_days:
        raise ValueError(f"days deve essere tra 1 e {max_days}")
    return value


@mcp.tool()
def today_snapshot() -> str:
    """Oggi: target, pasti, carico, readiness e promemoria."""
    return local.today_snapshot()


@mcp.tool()
def get_health_overview(days: int = 7) -> str:
    """Dati Health Connect disponibili: giorni, passi, calorie, sonno, HRV e sintesi battiti.
    days: 1..30. Non inventa valori mancanti o punteggi di recupero.
    """
    n = _days(days)
    start = (date.today() - timedelta(days=n - 1)).isoformat()
    c = db.connect()
    try:
        health_sync.initialize(c)
        def rows(query, args=(start,)):
            return [dict(r) for r in c.execute(query, args).fetchall()]
        daily = rows("SELECT date,steps,active_kcal,total_kcal,resting_hr,weight_kg,source "
                     "FROM days WHERE date >= ? ORDER BY date DESC LIMIT 30")
        sleeps = rows("SELECT night_date,start,stop,total_min,deep_min,light_min,rem_min,awake_min,score,source "
                      "FROM sleeps WHERE night_date >= ? ORDER BY night_date DESC LIMIT 30")
        hrv = rows("SELECT night_date,rmssd_ms,sdnn_ms,source FROM hrv_daily "
                   "WHERE night_date >= ? ORDER BY night_date DESC LIMIT 30")
        hr = rows("SELECT substr(ts,1,10) AS utc_date,COUNT(*) AS samples,MIN(bpm) AS min_bpm,"
                  "ROUND(AVG(bpm),1) AS avg_bpm,MAX(bpm) AS max_bpm FROM hr_samples "
                  "WHERE substr(ts,1,10) >= ? GROUP BY substr(ts,1,10) ORDER BY utc_date DESC LIMIT 30")
        events = rows("SELECT kind,title,start_at,end_at,duration_min,origin FROM hc_events "
                      "WHERE substr(start_at,1,10) >= ? ORDER BY start_at DESC LIMIT 100")
        return json.dumps({"range_from": start, "daily": daily, "sleep": sleeps,
                           "hrv": hrv, "heart_rate_by_utc_date": hr,
                           "health_connect_sessions_raw": events,
                           "sync_status": health_sync.status(c)}, ensure_ascii=False)
    finally:
        c.close()


@mcp.tool()
def get_readiness(days: int = 14) -> str:
    """Analizza il recupero degli ultimi 1-30 giorni; esplicita quando mancano HRV o dati sonno."""
    return local.get_readiness(_days(days))


@mcp.tool()
def get_workouts(days: int = 30) -> str:
    """Diario degli allenamenti registrati negli ultimi 1-90 giorni."""
    return local.get_workouts(_days(days, 90))


@mcp.tool()
def get_training_load(days: int = 30) -> str:
    """Andamento carico CTL/ATL/TSB negli ultimi 1-90 giorni."""
    return local.get_training_load(_days(days, 90))


@mcp.tool()
def get_nutrition(date: str = "") -> str:
    """Target e pasti del giorno indicato (YYYY-MM-DD; vuoto significa oggi)."""
    if date:
        from datetime import date as d
        d.fromisoformat(date)
    return local.get_nutrition(date or None)


@mcp.tool()
def log_meal(meal: str, kcal: float, protein_g: float, carbs_g: float, fat_g: float,
             description: str = "") -> str:
    """Registra un pasto effettivamente consumato. Da foto stima calorie e macro,
    segnalando che sono stime; chiedi conferma per cibi/quantità ambigui.
    meal: breakfast|lunch|dinner|snack.
    """
    import math
    if meal not in {"breakfast", "lunch", "dinner", "snack"}:
        raise ValueError("meal non valido")
    for value, limit in [(kcal, 10000), (protein_g, 800), (carbs_g, 1500), (fat_g, 800)]:
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not (0 <= value <= limit):
            raise ValueError("kcal/macronutrienti non validi")
    return local.log_meal(meal, kcal, protein_g, carbs_g, fat_g, description[:1000])


@mcp.tool()
def log_workout(date: str, type: str, duration_min: float, rpe: float | None = None,
                avg_hr: int | None = None, notes: str = "") -> str:
    """Registra solo allenamenti realmente svolti. Da foto WOD ricava la descrizione,
    ma NON inventare durata, risultato o RPE: chiedili all'utente.
    """
    from datetime import date as d
    d.fromisoformat(date)
    if type not in {"strength", "metcon", "gymnastics", "skill", "tennis", "other"}:
        raise ValueError("type non valido")
    if not 1 <= duration_min <= 360:
        raise ValueError("durata non valida")
    if rpe is not None and not 1 <= rpe <= 10:
        raise ValueError("RPE non valido")
    return local.log_workout(date, type, duration_min, rpe, avg_hr, notes[:1000])


for name in ("list_wods", "add_wod", "log_wod_result", "get_wod_history", "get_prs", "set_profile"):
    mcp.tool()(getattr(local, name))


def main() -> None:
    token = _token()
    # MCP 1.30 abilita il filtro DNS rebinding per default: autorizziamo
    # esplicitamente solo il nostro host HTTPS e il nome interno Docker.
    security = mcp.settings.transport_security
    security.enable_dns_rebinding_protection = True
    security.allowed_hosts = [
        "mcp-benessere.45-77-66-215.nip.io",
        "mcp-benessere.45-77-66-215.nip.io:443",
        "benessere-mcp:8000",
        "127.0.0.1:8000",
        "localhost:8000",
    ]
    security.allowed_origins = [
        "https://chatgpt.com",
        "https://chat.openai.com",
        "https://dashboard-benessere.45-77-66-215.nip.io",
        "https://mcp-benessere.45-77-66-215.nip.io",
    ]
    # Il token va letto prima del bind: non avviare senza autenticazione.
    app = mcp.streamable_http_app()
    app.add_middleware(RequireBearer, token=token)
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)


if __name__ == "__main__":
    main()
