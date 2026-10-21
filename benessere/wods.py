"""WOD: catalogo (benchmark + custom), risultati con punteggi normalizzati, PR tracking."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass

SCORE_TYPES = {"time", "amrap", "load", "reps"}
# time: meno è meglio; tutti gli altri: più è meglio
LOWER_IS_BETTER = {"time"}


@dataclass
class Wod:
    name: str
    score_type: str
    category: str = "custom"
    description: str = ""
    custom: int = 0
    id: int | None = None


def parse_score(score_type: str, raw: str) -> float:
    """Converte l'input utente in score_value normalizzato.

    time:  "3:45" o "225" → secondi
    amrap: "12+35"        → 12.35 (rounds.reps frazionari)
    load:  "142.5"        → kg
    reps:  "87"           → ripetizioni
    """
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("punteggio vuoto")
    if score_type == "time":
        if ":" in raw:
            parts = raw.split(":")
            if len(parts) != 2:
                raise ValueError(f"tempo non valido: {raw} (usa mm:ss)")
            m, s = int(parts[0]), int(parts[1])
            if s >= 60 or m < 0:
                raise ValueError(f"tempo non valido: {raw}")
            return float(m * 60 + s)
        v = float(raw)
        if v <= 0:
            raise ValueError("i secondi devono essere > 0")
        return v
    if score_type == "amrap":
        if "+" not in raw:
            rounds = float(raw)
            return rounds
        r, reps = raw.split("+", 1)
        rounds, reps = float(r), float(reps)
        if rounds < 0 or not 0 <= reps:
            raise ValueError(f"amrap non valido: {raw}")
        return rounds + min(reps, 99) / 100.0
    if score_type in {"load", "reps"}:
        v = float(raw)
        if v <= 0:
            raise ValueError("il valore deve essere > 0")
        return v
    raise ValueError(f"score_type non valido: {score_type}")


def format_score(score_type: str, value: float) -> str:
    if score_type == "time":
        m, s = divmod(int(round(value)), 60)
        return f"{m}:{s:02d}"
    if score_type == "amrap":
        rounds = int(value)
        reps = round((value - rounds) * 100)
        return f"{rounds}+{reps}" if reps else f"{rounds}"
    if score_type == "load":
        return f"{value:g} kg"
    return str(int(value))


def add_wod(conn: sqlite3.Connection, w: Wod) -> int:
    if w.score_type not in SCORE_TYPES:
        raise ValueError(f"score_type non valido: {w.score_type}")
    conn.execute(
        "INSERT INTO wods(name, category, score_type, description, custom) VALUES(?,?,?,?,?) "
        "ON CONFLICT(name) DO NOTHING",
        (w.name, w.category, w.score_type, w.description, w.custom),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM wods WHERE name=?", (w.name,)).fetchone()
    return int(row["id"])


def list_wods(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM wods ORDER BY custom, category, name").fetchall()


def get_wod(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM wods WHERE name = ? COLLATE NOCASE", (name,)).fetchone()


def add_result(
    conn: sqlite3.Connection,
    wod_name: str,
    date_s: str,
    raw_score: str,
    scaling: str = "rx",
    notes: str = "",
) -> dict:
    wod = get_wod(conn, wod_name)
    if wod is None:
        raise ValueError(f"WOD sconosciuto: {wod_name} (crealo prima con add_wod)")
    value = parse_score(wod["score_type"], raw_score)
    better = (
        (lambda new, old: new < old) if wod["score_type"] in LOWER_IS_BETTER else (lambda new, old: new > old)
    )
    prior = conn.execute(
        "SELECT score_value FROM wod_results WHERE wod_id=? AND scaling=?", (wod["id"], scaling),
    ).fetchall()
    is_pr = int(all(better(value, p["score_value"]) for p in prior)) if prior else 1
    cur = conn.execute(
        "INSERT INTO wod_results(wod_id, date, score_value, score_display, scaling, notes, is_pr) "
        "VALUES(?,?,?,?,?,?,?)",
        (wod["id"], date_s, value, raw_score.strip(), scaling, notes, is_pr),
    )
    conn.commit()
    return {"id": int(cur.lastrowid), "wod": wod["name"], "score": raw_score.strip(), "scaling": scaling, "is_pr": bool(is_pr)}


def results_for(conn: sqlite3.Connection, wod_name: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT wr.*, w.name AS wod, w.score_type FROM wod_results wr JOIN wods w ON w.id=wr.wod_id "
        "WHERE w.name = ? COLLATE NOCASE ORDER BY wr.date, wr.id",
        (wod_name,),
    ).fetchall()


def prs(conn: sqlite3.Connection) -> list[dict]:
    """Miglior risultato per (wod, scaling)."""
    out: list[dict] = []
    for w in list_wods(conn):
        for scaling in {r["scaling"] for r in results_for(conn, w["name"])}:
            rows = results_for(conn, w["name"])
            rows = [r for r in rows if r["scaling"] == scaling]
            best = (
                min(rows, key=lambda r: r["score_value"]) if w["score_type"] in LOWER_IS_BETTER else max(rows, key=lambda r: r["score_value"])
            )
            out.append(
                {
                    "wod": w["name"],
                    "scaling": scaling,
                    "score": best["score_display"],
                    "date": best["date"],
                    "score_type": w["score_type"],
                }
            )
    return out


def delete_result(conn: sqlite3.Connection, result_id: int) -> None:
    conn.execute("DELETE FROM wod_results WHERE id=?", (result_id,))
    conn.commit()
