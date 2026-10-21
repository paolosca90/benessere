"""Rimozione conservativa dei soli dati dimostrativi identificabili.

Non tocca mai i WOD con risultati, né allenamenti o pasti effettivi.
Prima di qualsiasi aggiornamento sul database esegue un backup SQLite consistente.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3

from .seed_wods import BENCHMARKS

MIGRATION_ID = "remove_legacy_seed_wods_and_synthetic_bridge_load_v1"

def preview(conn: sqlite3.Connection) -> dict[str, int]:
    known = tuple(b.name for b in BENCHMARKS)
    marks = ",".join("?" for _ in known)
    seed = conn.execute(
        f"SELECT COUNT(*) n FROM wods WHERE custom=0 AND name IN ({marks}) "
        "AND NOT EXISTS (SELECT 1 FROM wod_results r WHERE r.wod_id=wods.id)", known
    ).fetchone()["n"]
    synthetic = conn.execute(
        "SELECT COUNT(*) n FROM workouts WHERE source='chatgpt_sheets' AND rpe IS NULL "
        "AND avg_hr IS NULL AND load IS NOT NULL AND ABS(load - duration_min*3.0)<0.01"
    ).fetchone()["n"]
    return {"seed_rows_without_results": seed, "synthetic_training_loads": synthetic}

def migrate(conn: sqlite3.Connection, path: Path) -> dict[str, int]:
    conn.execute("CREATE TABLE IF NOT EXISTS app_migrations (name TEXT PRIMARY KEY, applied_at TEXT DEFAULT (datetime('now')))")
    if conn.execute("SELECT name FROM app_migrations WHERE name=?", (MIGRATION_ID,)).fetchone():
        return {"seed_rows_without_results": 0, "synthetic_training_loads": 0}
    count = preview(conn)
    if any(count.values()):
        path=Path(path)
        stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup=path.parent / f"benessere.backup-before-cleanup-{stamp}.sqlite3"
        # Il backup non parte se manca lo spazio: il database resta intatto.
        dest=sqlite3.connect(str(backup))
        try:
            conn.backup(dest)
        finally:
            dest.close()
        try:
            os.chmod(backup,0o600)
        except OSError:
            pass
        names=tuple(b.name for b in BENCHMARKS)
        slots=",".join("?" for _ in names)
        with conn:
            conn.execute(
                f"DELETE FROM wods WHERE custom=0 AND name IN ({slots}) "
                "AND NOT EXISTS(SELECT 1 FROM wod_results wr WHERE wr.wod_id=wods.id)",names)
            conn.execute(
                "UPDATE workouts SET load=NULL WHERE source='chatgpt_sheets' AND rpe IS NULL "
                "AND avg_hr IS NULL AND load IS NOT NULL AND ABS(load-duration_min*3.0)<0.01"
            )
            conn.execute("INSERT OR IGNORE INTO app_migrations(name) VALUES(?)",(MIGRATION_ID,))
    else:
        with conn:
            conn.execute("INSERT OR IGNORE INTO app_migrations(name) VALUES(?)",(MIGRATION_ID,))
    return count
