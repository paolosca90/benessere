"""Dettagli temporali delle sessioni: blocchi ordinati e provenienza dichiarata."""
from __future__ import annotations

from datetime import date, datetime
import math
import sqlite3

SCHEMA="""
CREATE TABLE IF NOT EXISTS workout_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id INTEGER NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    phase TEXT NOT NULL,
    label TEXT NOT NULL,
    exercise TEXT NOT NULL,
    repetitions INTEGER,
    sets INTEGER,
    weight_kg REAL,
    start_offset_min REAL,
    end_offset_min REAL,
    reported_duration_min REAL,
    time_reference TEXT NOT NULL DEFAULT 'workout',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(workout_id,position)
);
CREATE INDEX IF NOT EXISTS idx_workout_blocks_workout ON workout_blocks(workout_id,position);
"""
PHASES={"strength","skill","warmup","wod","other"}
REFERENCES={"workout","wod","unspecified"}

def initialize(conn:sqlite3.Connection)->None:
    cols={r["name"] for r in conn.execute("PRAGMA table_info(workouts)")}
    if "start_time" not in cols:
        conn.execute("ALTER TABLE workouts ADD COLUMN start_time TEXT")
    if "wod_result_id" not in cols:
        conn.execute("ALTER TABLE workouts ADD COLUMN wod_result_id INTEGER")
    conn.executescript(SCHEMA)

def normalized_blocks(blocks:list[dict])->list[dict]:
    if not isinstance(blocks,list) or not 1 <= len(blocks) <= 30:
        raise ValueError("La sessione richiede da 1 a 30 blocchi")
    out=[]
    for index,b in enumerate(blocks,1):
        if not isinstance(b,dict):
            raise ValueError(f"Blocco {index} non valido")
        phase=b.get("phase","other")
        reference=b.get("time_reference","unspecified")
        label=str(b.get("label") or "").strip()
        exercise=str(b.get("exercise") or "").strip()
        notes=str(b.get("notes") or "")
        if phase not in PHASES or reference not in REFERENCES or not label or not exercise:
            raise ValueError(f"Blocco {index}: tipo, riferimento, etichetta o esercizio non validi")
        if len(label)>70 or len(exercise)>180 or len(notes)>650:
            raise ValueError(f"Blocco {index}: descrizione troppo lunga")
        clean={"position":index,"phase":phase,"label":label,
               "exercise":exercise,"time_reference":reference,"notes":notes}
        for field,limit in (("repetitions",10000),("sets",1000)):
            v=b.get(field)
            if v is not None:
                if isinstance(v,bool) or not isinstance(v,int) or not 1<=v<=limit:
                    raise ValueError(f"Blocco {index}: {field} non valido")
            clean[field]=v
        for field,limit in (("weight_kg",1000.0),("start_offset_min",360.0),
                            ("end_offset_min",360.0),("reported_duration_min",360.0)):
            v=b.get(field)
            if v is not None:
                v=float(v)
                if not math.isfinite(v) or v<0 or v>limit or (field in ("weight_kg","reported_duration_min") and v==0):
                    raise ValueError(f"Blocco {index}: {field} fuori intervallo")
            clean[field]=v
        if clean["start_offset_min"] is not None and clean["end_offset_min"] is not None:
            if clean["end_offset_min"]<=clean["start_offset_min"]:
                raise ValueError(f"Blocco {index}: fine prima dell'inizio")
            dur=clean["reported_duration_min"]
            # Se l'utente dà inizio/fine relativi e durata, devono combaciare.
            if dur is not None and abs(clean["end_offset_min"]-clean["start_offset_min"]-dur)>.1:
                raise ValueError(f"Blocco {index}: durata e intervallo discordanti")
        out.append(clean)
    return out

def replace_blocks_in_transaction(conn:sqlite3.Connection,workout_id:int,blocks:list[dict])->int:
    """Da chiamare all'interno di BEGIN/COMMIT esterni per aggiornamento atomico."""
    clean=normalized_blocks(blocks)
    # Schema gia inizializzato prima di BEGIN: executescript committerebbe la transazione.
    row=conn.execute("SELECT id FROM workouts WHERE id=?",(workout_id,)).fetchone()
    if not row:raise ValueError("Allenamento inesistente")
    conn.execute("DELETE FROM workout_blocks WHERE workout_id=?",(workout_id,))
    for item in clean:
        conn.execute(
            """INSERT INTO workout_blocks (
            workout_id,position,phase,label,exercise,repetitions,sets,weight_kg,
            start_offset_min,end_offset_min,reported_duration_min,time_reference,notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (workout_id, item["position"],item["phase"],item["label"],item["exercise"],
             item["repetitions"],item["sets"],item["weight_kg"],item["start_offset_min"],
             item["end_offset_min"],item["reported_duration_min"],item["time_reference"],
             item["notes"])
        )
    return len(clean)

def append_block(conn:sqlite3.Connection, workout_id:int, block:dict)->int:
    initialize(conn)
    item=normalized_blocks([block])[0]
    if not conn.execute("SELECT id FROM workouts WHERE id=?",(workout_id,)).fetchone():
        raise ValueError("Allenamento inesistente")
    with conn:
        position=conn.execute(
            "SELECT COALESCE(MAX(position),0)+1 FROM workout_blocks WHERE workout_id=?",
            (workout_id,)
        ).fetchone()[0]
        cursor=conn.execute(
            """INSERT INTO workout_blocks(
            workout_id,position,phase,label,exercise,repetitions,sets,weight_kg,
            start_offset_min,end_offset_min,reported_duration_min,time_reference,notes
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (workout_id,position,item["phase"],item["label"],item["exercise"],
             item["repetitions"],item["sets"],item["weight_kg"],item["start_offset_min"],
             item["end_offset_min"],item["reported_duration_min"],item["time_reference"],
             item["notes"])
        )
    return int(cursor.lastrowid)

def remove_block(conn:sqlite3.Connection, workout_id:int, block_id:int)->bool:
    initialize(conn)
    with conn:
        changed=conn.execute(
            "DELETE FROM workout_blocks WHERE id=? AND workout_id=?",
            (block_id,workout_id)
        ).rowcount
    return bool(changed)

def blocks_for(conn:sqlite3.Connection,workout_id:int)->list[dict]:
    initialize(conn)
    return [dict(r) for r in conn.execute(
        "SELECT * FROM workout_blocks WHERE workout_id=? ORDER BY position",(workout_id,)
    ).fetchall()]

def start_time_string(v:str)->str:
    if not isinstance(v,str):
        raise ValueError("Orario di inizio richiesto")
    return datetime.strptime(v,"%H:%M").strftime("%H:%M")

def timeline_warnings(blocks:list[dict], total_wod_min:float|None=None)->list[str]:
    """Segnala dati temporali incompatibili SENZA cambiare le misure fornite."""
    warnings=[]
    seq=[b for b in blocks if b.get("phase")=="wod"
         and b.get("time_reference")=="wod"
         and b.get("start_offset_min") is not None
         and b.get("reported_duration_min") is not None]
    if seq and total_wod_min is not None:
        max_end=max(float(b["start_offset_min"])+float(b["reported_duration_min"]) for b in seq)
        if max_end>float(total_wod_min)+.1:
            warnings.append(
                f"Ultimo termine teorico WOD {max_end:g}′, ma totale dichiarato {total_wod_min:g}′: "
                "partenze e tempi parziali richiedono verifica"
            )
    return warnings
