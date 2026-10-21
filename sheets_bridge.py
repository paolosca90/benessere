"""Ricevitore privato per la coda Google Sheets Benessere.

Avvio: BENESSERE_BRIDGE_TOKEN_FILE=/run/secrets/bridge_token python sheets_bridge.py
Usare SOLO dietro reverse proxy HTTPS. Nessun dato sanitario nei log.
"""
from __future__ import annotations
import hmac
import json
import os
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from benessere import db, maxes, nutrition, workouts, wods

MAX_BYTES = 65536

def apply_workout_revision(conn, key: str, data: dict) -> dict:
    """Rettifica un allenamento IMPORTATO senza creare una seconda sessione."""
    from benessere import workout_details as details
    source=str(data.get("update_of") or "")
    if not source or source == key:
        raise ValueError("ID allenamento originale mancante")
    original=conn.execute(
        "SELECT kind,result_json FROM sheets_bridge_events WHERE event_id=?",(source,)
    ).fetchone()
    if not original or original["kind"]!="workout":
        raise ValueError("Evento workout originale non trovato")
    first=json.loads(original["result_json"])
    workout_id=first.get("workout_id")
    wod_id=first.get("wod_result_id")
    if not isinstance(workout_id,int):
        raise ValueError("Riferimento workout mancante")
    previous=conn.execute("SELECT * FROM workouts WHERE id=?",(workout_id,)).fetchone()
    if not previous or previous["source"]!="chatgpt_sheets":
        raise ValueError("Allenamento originale non modificabile")
    if data.get("date") != previous["date"]:
        raise ValueError("La data originale non puo' cambiare")
    start_time=details.start_time_string(data["start_time"])
    duration=float(data.get("duration_min",previous["duration_min"]))
    if not 1 <= duration <= 360:
        raise ValueError("Durata sessione fuori intervallo")
    notes=str(data.get("notes",""))
    if not notes or len(notes)>1000:
        raise ValueError("Note della rettifica non valide")
    blocks=details.normalized_blocks(data["blocks"])
    original_wod=conn.execute("SELECT * FROM wod_results WHERE id=?",(wod_id,)).fetchone() if wod_id else None
    total=original_wod["score_value"]/60 if original_wod else None
    warnings=details.timeline_warnings(blocks,total)
    wod_notes=str(data.get("wod_notes",""))
    if len(wod_notes)>1000:
        raise ValueError("Note WOD troppo lunghe")
    details.initialize(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        again=conn.execute("SELECT result_json FROM sheets_bridge_events WHERE event_id=?",(key,)).fetchone()
        if again:
            conn.rollback()
            return {"status":"duplicate","result":json.loads(again["result_json"])}
        conn.execute("UPDATE workouts SET start_time=?,duration_min=?,notes=?,wod_result_id=? WHERE id=?",
                     (start_time,duration,notes,wod_id,workout_id))
        count=details.replace_blocks_in_transaction(conn,workout_id,blocks)
        if wod_id and wod_notes:
            conn.execute("UPDATE wod_results SET notes=? WHERE id=?",(wod_notes,wod_id))
        result={"workout_id":workout_id,"wod_result_id":wod_id,
                "blocks_updated":count,"timeline_warnings":warnings}
        conn.execute("INSERT INTO sheets_bridge_events(event_id,kind,result_json) VALUES(?,?,?)",
                     (key,"workout",json.dumps(result,ensure_ascii=False)))
        conn.commit()
        return {"status":"saved","result":result}
    except Exception:
        conn.rollback()
        raise

def apply_event(conn, key: str, kind: str, data: dict) -> dict:
    if not isinstance(key, str) or not 4 <= len(key) <= 128 or not all(c.isalnum() or c in '_-' for c in key):
        raise ValueError("ID non valido")
    if not isinstance(data, dict):
        raise ValueError("JSON non valido")
    conn.execute("CREATE TABLE IF NOT EXISTS sheets_bridge_events (event_id TEXT PRIMARY KEY, kind TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')))")
    prior = conn.execute("SELECT result_json FROM sheets_bridge_events WHERE event_id=?", (key,)).fetchone()
    if prior:
        return {"status": "duplicate", "result": json.loads(prior["result_json"])}
    if kind == "workout" and data.get("update_of"):
        return apply_workout_revision(conn,key,data)
    if kind == "workout":
        day = date.fromisoformat(data["date"]).isoformat()
        duration = float(data["duration_min"])
        typ = data.get("type", "other")
        if typ not in workouts.VALID_TYPES or not 1 <= duration <= 360:
            raise ValueError("tipo o durata non validi")
        rpe = data.get("rpe")
        if rpe is not None and not 1 <= float(rpe) <= 10:
            raise ValueError("RPE non valido")
        notes = str(data.get("notes", ""))[:1000]
        wod = data.get("wod")
        if wod:
            if not isinstance(wod, dict) or wod.get("score_type") not in wods.SCORE_TYPES:
                raise ValueError("WOD non valido")
            score = str(wod["score"])
            wods.parse_score(wod["score_type"], score)
            existing = wods.get_wod(conn, str(wod["name"]))
            if existing and existing["score_type"] != wod["score_type"]:
                raise ValueError("Nome WOD gia usato con score_type diverso")
        # Transazione atomica: nessun commit intermedio sui due inserimenti.
        conn.execute("BEGIN IMMEDIATE")
        try:
            prior_txn = conn.execute("SELECT result_json FROM sheets_bridge_events WHERE event_id=?", (key,)).fetchone()
            if prior_txn:
                conn.rollback()
                return {"status": "duplicate", "result": json.loads(prior_txn["result_json"])}
            if wod:
                name = str(wod["name"])[:160]
                conn.execute("INSERT OR IGNORE INTO wods(name,category,score_type,description,custom) VALUES(?,?,?,?,1)",
                             (name, str(wod.get("category","custom"))[:30], wod["score_type"], str(wod.get("description",""))[:1000]))
                w = wods.get_wod(conn, name)
                value = wods.parse_score(wod["score_type"], str(wod["score"]))
                scaling = str(wod.get("scaling") or "unspecified")[:30]
                previous = conn.execute("SELECT score_value FROM wod_results WHERE wod_id=? AND scaling=?", (w["id"],scaling)).fetchall()
                better = (lambda new,old: new < old) if wod["score_type"] == "time" else (lambda new,old: new > old)
                pr = int(all(better(value,x["score_value"]) for x in previous))
                c = conn.execute("INSERT INTO wod_results(wod_id,date,score_value,score_display,scaling,notes,is_pr) VALUES(?,?,?,?,?,?,?)",
                          (w["id"],day,value,str(wod["score"]),scaling,str(wod.get("notes",""))[:1000],pr))
                wod_id = c.lastrowid
            else:
                wod_id = None
            load = workouts.compute_load(conn, typ, duration, float(rpe) if rpe is not None else None, None)
            c = conn.execute("INSERT INTO workouts(date,type,duration_min,rpe,load,notes,source) VALUES(?,?,?,?,?,?,?)",
                            (day,typ,duration,float(rpe) if rpe is not None else None,load,notes,"chatgpt_sheets"))
            result = {"workout_id":c.lastrowid,"wod_result_id":wod_id}
            conn.execute("INSERT INTO sheets_bridge_events(event_id,kind,result_json) VALUES(?,?,?)",(key,kind,json.dumps(result)))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    elif kind == "meal":
        day = date.fromisoformat(data["date"]).isoformat()
        meal = str(data["meal"])
        if meal not in {"breakfast","lunch","dinner","snack"}:
            raise ValueError("tipo pasto non valido")
        hhmm = str(data["time"])
        tm = datetime.strptime(hhmm,"%H:%M").strftime("%H:%M")
        amounts = [float(data[x]) for x in ("kcal","protein_g","carbs_g","fat_g")]
        import math
        if any(not math.isfinite(v) or v < 0 or v > cap for v,cap in zip(amounts,(10000,800,1500,800))):
            raise ValueError("macronutrienti non validi")
        ts = f"{day}T{tm}:00"
        conn.execute("BEGIN IMMEDIATE")
        try:
            prior_txn = conn.execute("SELECT result_json FROM sheets_bridge_events WHERE event_id=?", (key,)).fetchone()
            if prior_txn:
                conn.rollback()
                return {"status": "duplicate", "result": json.loads(prior_txn["result_json"])}
            # Se la stessa ora e' gia' stata usata, NON sovrascrivere un pasto registrato fuori dal bridge.
            existing = conn.execute("SELECT ts FROM meals WHERE ts=?",(ts,)).fetchone()
            if existing:
                raise ValueError("Pasto gia presente nello stesso minuto: cambiare orario o verificare")
            conn.execute("INSERT INTO meals(ts,meal,description,kcal,protein_g,carbs_g,fat_g) VALUES(?,?,?,?,?,?,?)",
                         (ts,meal,str(data.get("description",""))[:1000],*amounts))
            result = {"meal_ts":ts}
            conn.execute("INSERT INTO sheets_bridge_events(event_id,kind,result_json) VALUES(?,?,?)",(key,kind,json.dumps(result)))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    elif kind == "max":
        import math
        day = maxes.valid_date(str(data["date"]))
        lift = str(data["lift"]).strip()
        weight = float(data["weight_kg"])
        reps = int(data.get("reps", 1))
        notes = str(data.get("notes", ""))
        if not lift or len(lift) > 100:
            raise ValueError("Esercizio non valido")
        if not math.isfinite(weight) or not 0 < weight <= 1000:
            raise ValueError("Peso non valido")
        if not 1 <= reps <= 100 or len(notes) > 1000:
            raise ValueError("Ripetizioni o note non valide")
        category = str(data.get("category", "lift"))
        if category not in maxes.CATEGORIES:
            raise ValueError("Categoria massimale non valida")
        maxes.initialize(conn)
        conn.execute("BEGIN IMMEDIATE")
        try:
            prior_txn = conn.execute("SELECT result_json FROM sheets_bridge_events WHERE event_id=?", (key,)).fetchone()
            if prior_txn:
                conn.rollback()
                return {"status": "duplicate", "result": json.loads(prior_txn["result_json"])}
            c = conn.execute(
                "INSERT INTO strength_maxes(lift,date,weight_kg,reps,notes,source,category) VALUES(?,?,?,?,?,?,?)",
                (lift,day,weight,reps,notes,"chatgpt_sheets",category),
            )
            result = {"max_id": c.lastrowid}
            conn.execute(
                "INSERT INTO sheets_bridge_events(event_id,kind,result_json) VALUES(?,?,?)",
                (key,kind,json.dumps(result)),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    elif kind == "profile":
        import math
        limits = {
            "height_cm": (90, 240),
            "weight_kg": (20, 350),
            "body_fat_pct_estimate": (1, 65),
        }
        updates = {}
        for field, value in data.items():
            if field not in limits:
                raise ValueError("Proprieta' profilo non supportata")
            value = float(value)
            lo, hi = limits[field]
            if not math.isfinite(value) or not lo <= value <= hi:
                raise ValueError("Valore profilo fuori intervallo")
            updates[field] = value
        if not updates:
            raise ValueError("Nessun dato profilo")
        conn.execute("BEGIN IMMEDIATE")
        try:
            already = conn.execute("SELECT result_json FROM sheets_bridge_events WHERE event_id=?", (key,)).fetchone()
            if already:
                conn.rollback()
                return {"status":"duplicate","result":json.loads(already["result_json"])}
            for k, value in updates.items():
                conn.execute(
                    "INSERT INTO profile(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (k,str(value)),
                )
            result = {"updated_fields": list(updates)}
            conn.execute("INSERT INTO sheets_bridge_events(event_id,kind,result_json) VALUES(?,?,?)",
                         (key,kind,json.dumps(result)))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    else:
        raise ValueError("Tipo evento non valido")
    return {"status":"saved","result":result}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def send(self, status, payload):
        raw=json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_POST(self):
        if self.path!="/bridge/v1/import":
            return self.send(404,{"error":"not_found"})
        if not hmac.compare_digest(self.headers.get("Authorization",""),"Bearer "+self.server.bridge_token):
            return self.send(401,{"error":"unauthorized"})
        try:
            size=int(self.headers.get("Content-Length","0"))
            if not 0<size<=MAX_BYTES:
                return self.send(413,{"error":"payload_size"})
            payload=json.loads(self.rfile.read(size))
            conn=db.connect()
            try:
                outcome=apply_event(conn,payload["id"],payload["type"],payload["data"])
            finally:
                conn.close()
            return self.send(200,outcome)
        except (ValueError,KeyError,TypeError,OverflowError) as e:
            return self.send(400,{"error":str(e)[:180]})
        except Exception:
            return self.send(500,{"error":"internal_error"})

class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self, address, token):
        super().__init__(address,Handler)
        self.bridge_token=token

if __name__=="__main__":
    path=os.environ.get("BENESSERE_BRIDGE_TOKEN_FILE")
    token=Path(path).read_text().strip() if path else os.environ.get("BENESSERE_BRIDGE_TOKEN","").strip()
    if len(token)<32: raise RuntimeError("Token bridge mancante")
    Server(("0.0.0.0",int(os.environ.get("PORT","8010"))),token).serve_forever()
