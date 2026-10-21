"""Progress photo archive; private images, remove metadata and compare by date."""
from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
import os
import sqlite3
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES=10*1024*1024
ANGLES=("front","side","back","other")
SCHEMA="""
CREATE TABLE IF NOT EXISTS progress_photos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  taken_on TEXT NOT NULL,
  angle TEXT NOT NULL,
  filename TEXT NOT NULL UNIQUE,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_progress_photos_date ON progress_photos(taken_on DESC);
"""

def initialize(conn:sqlite3.Connection)->None:
    conn.executescript(SCHEMA)

def photo_dir(db_file:Path)->Path:
    return Path(db_file).resolve().parent / "photos"

def add_photo(conn:sqlite3.Connection, db_file:Path, taken_on:str,
              angle:str, contents:bytes, notes:str="")->int:
    date.fromisoformat(taken_on)
    if angle not in ANGLES:
        raise ValueError("Inquadratura non valida")
    if not contents or len(contents)>MAX_UPLOAD_BYTES:
        raise ValueError("Foto vuota o superiore a 10 MB")
    if len(notes)>600:
        raise ValueError("Note troppo lunghe")
    try:
        with Image.open(BytesIO(contents)) as raw:
            if raw.width*raw.height>32_000_000:
                raise ValueError("Risoluzione eccessiva")
            raw.load()
            img=ImageOps.exif_transpose(raw).convert("RGB")
            img.thumbnail((2048,2048),Image.Resampling.LANCZOS)
            safe=BytesIO()
            img.save(safe,format="JPEG",quality=86,optimize=True)
    except (UnidentifiedImageError,Image.DecompressionBombError,OSError) as exc:
        raise ValueError("Formato immagine non valido") from exc
    initialize(conn)
    directory=photo_dir(db_file)
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    try:os.chmod(directory,0o700)
    except OSError:pass
    name=uuid.uuid4().hex+".jpg"
    dst=directory/name
    try:
        with dst.open("xb") as f:
            f.write(safe.getvalue())
        try:os.chmod(dst,0o600)
        except OSError:pass
        with conn:
            cursor=conn.execute("INSERT INTO progress_photos(taken_on,angle,filename,notes) VALUES(?,?,?,?)",
                (taken_on,angle,name,notes))
        return int(cursor.lastrowid)
    except Exception:
        dst.unlink(missing_ok=True)
        raise

def entries(conn:sqlite3.Connection)->list[sqlite3.Row]:
    initialize(conn)
    return conn.execute("SELECT * FROM progress_photos ORDER BY taken_on DESC,id DESC").fetchall()

def photo_bytes(db_file:Path,filename:str)->bytes:
    path=Path(filename)
    if path.name != filename or not filename.endswith(".jpg") or len(filename)!=36:
        raise ValueError("Nome file non valido")
    return (photo_dir(db_file)/filename).read_bytes()

def remove_photo(conn:sqlite3.Connection,db_file:Path,identifier:int)->bool:
    initialize(conn)
    row=conn.execute("SELECT filename FROM progress_photos WHERE id=?",(identifier,)).fetchone()
    if row is None:return False
    file=photo_dir(db_file)/row["filename"]
    with conn:
        conn.execute("DELETE FROM progress_photos WHERE id=?",(identifier,))
    file.unlink(missing_ok=True)
    return True
