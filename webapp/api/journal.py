"""Journal API for Benessere PWA: reuse existing SQLite without data duplication.

All routes inherit bearer authentication from the FastAPI parent application.
These operations deliberately do not expose delete endpoints in the first release.
"""
from __future__ import annotations

import base64
import binascii
from datetime import date, datetime
from hashlib import sha256
import json
import math
import sqlite3
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from benessere import db, maxes, nutrition, nutrition_schedule, progress_photos, workout_details, workouts, wods
from .main import auth, connection

router = APIRouter(prefix="/v1", dependencies=[Depends(auth)])
ROME=ZoneInfo("Europe/Rome")

def _bad(exc:Exception):
    raise HTTPException(status_code=422, detail=str(exc)) from exc

def _idem_init(conn:sqlite3.Connection):
    conn.execute("""CREATE TABLE IF NOT EXISTS journal_request_keys (
        request_key TEXT PRIMARY KEY,
        record_type TEXT NOT NULL,
        record_id TEXT NOT NULL,
        payload_sha TEXT NOT NULL
    )""")

def _idempotent(conn:sqlite3.Connection, kind:str, key:UUID, body:dict, insert):
    _idem_init(conn)
    digest=sha256(json.dumps(body,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
    with conn:
        conn.execute("BEGIN IMMEDIATE") if not conn.in_transaction else None
        prior=conn.execute(
            "SELECT record_type,record_id,payload_sha FROM journal_request_keys WHERE request_key=?",
            (str(key),)).fetchone()
        if prior:
            if prior["record_type"]!=kind or prior["payload_sha"]!=digest:
                raise HTTPException(status_code=409,detail="Chiave operazione già usata per altri dati")
            return {"id":prior["record_id"],"saved":True,"already_exists":True}
        identifier=str(insert())
        conn.execute("INSERT INTO journal_request_keys VALUES(?,?,?,?)",
                     (str(key),kind,identifier,digest))
        return {"id":identifier,"saved":True,"already_exists":False}

class MealBody(BaseModel):
    model_config=ConfigDict(extra="forbid")
    request_key:UUID
    date:date
    meal:Literal["breakfast","lunch","dinner","snack"]
    description:str=Field(min_length=1,max_length=600)
    kcal:float=Field(ge=0,le=10000,allow_inf_nan=False)
    protein_g:float=Field(ge=0,le=800,allow_inf_nan=False)
    carbs_g:float=Field(ge=0,le=1500,allow_inf_nan=False)
    fat_g:float=Field(ge=0,le=800,allow_inf_nan=False)

class WorkoutBody(BaseModel):
    model_config=ConfigDict(extra="forbid")
    request_key:UUID
    date:date
    type:Literal["strength","metcon","gymnastics","skill","tennis","other"]
    duration_min:float=Field(gt=0,le=360,allow_inf_nan=False)
    rpe:float|None=Field(default=None,ge=1,le=10,allow_inf_nan=False)
    start_time:str|None=None
    notes:str=Field(default="",max_length=1500)

class MaxBody(BaseModel):
    model_config=ConfigDict(extra="forbid")
    lift:str=Field(min_length=1,max_length=160)
    date:str
    weight_kg:float=Field(gt=0,le=1000,allow_inf_nan=False)
    reps:int=Field(default=1,ge=1,le=100)
    category:Literal["lift","complex"]="lift"
    notes:str=Field(default="",max_length=1000)

class WodBody(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name:str=Field(min_length=1,max_length=150)
    score_type:Literal["time","amrap","load","reps"]
    description:str=Field(default="",max_length=1000)

class ResultBody(BaseModel):
    model_config=ConfigDict(extra="forbid")
    wod_name:str=Field(min_length=1,max_length=150)
    date:date
    score:str=Field(min_length=1,max_length=30)
    scaling:str=Field(default="rx",min_length=1,max_length=70)
    notes:str=Field(default="",max_length=500)

class PhotoBody(BaseModel):
    model_config=ConfigDict(extra="forbid")
    taken_on:date
    angle:Literal["front","side","back","other"]
    image_base64:str=Field(min_length=10,max_length=15_000_000)
    notes:str=Field(default="",max_length=600)

class ProfileBody(BaseModel):
    model_config=ConfigDict(extra="forbid")
    goal:Literal["cut","maintain","bulk"]|None=None
    sex:Literal["m","f"]|None=None
    height_cm:float|None=Field(default=None,ge=90,le=240,allow_inf_nan=False)
    weight_kg:float|None=Field(default=None,ge=20,le=350,allow_inf_nan=False)
    age:int|None=Field(default=None,ge=14,le=100)
    sleep_need_h:float|None=Field(default=None,ge=4,le=12,allow_inf_nan=False)
    resting_hr:int|None=Field(default=None,ge=30,le=120)
    body_fat_pct_estimate:float|None=Field(default=None,ge=1,le=65,allow_inf_nan=False)

class BlockBody(BaseModel):
    model_config=ConfigDict(extra="forbid")
    workout_id:int=Field(gt=0)
    phase:Literal["strength","skill","warmup","wod","other"]="other"
    label:str=Field(min_length=1,max_length=70)
    exercise:str=Field(min_length=1,max_length=180)
    repetitions:int|None=Field(default=None,ge=1,le=10000)
    sets:int|None=Field(default=None,ge=1,le=1000)
    weight_kg:float|None=Field(default=None,ge=0,le=1000,allow_inf_nan=False)
    rpe:float|None=Field(default=None,ge=1,le=10,allow_inf_nan=False)
    time_reference:Literal["workout","wod","unspecified"]="unspecified"
    notes:str=Field(default="",max_length=650)

class ModeBody(BaseModel):
    model_config=ConfigDict(extra="forbid")
    date:date
    mode:Literal["crossfit_hard","crossfit_light","tennis","double","rest","unspecified"]

@router.get("/journal")
def journal(kind:Literal["meals","workouts","wods","results","maxes","photos","profile"],
            day:date|None=None,conn=Depends(connection)):
    if kind=="meals":
        d=day or datetime.now(ROME).date()
        rows=nutrition.meals_for_day(conn,d.isoformat())
        return {"items":[dict(x) for x in rows],"date":d.isoformat()}
    if kind=="workouts":
        d=day or datetime.now(ROME).date()
        records=[dict(x) for x in conn.execute(
            "SELECT * FROM workouts WHERE date=? ORDER BY id DESC",(d.isoformat(),))]
        for x in records:
            x["blocks"]=workout_details.blocks_for(conn,x["id"])
        return {"items":records,"date":d.isoformat()}
    if kind=="wods":
        return {"items":[dict(x) for x in wods.list_wods(conn)]}
    if kind=="results":
        return {"items":[dict(x) for x in conn.execute(
            "SELECT wr.*,w.name AS wod,w.score_type FROM wod_results wr "
            "JOIN wods w ON wr.wod_id=w.id ORDER BY wr.date DESC,wr.id DESC LIMIT 300")]}
    if kind=="maxes":
        return {"items":[dict(x) for x in maxes.history(conn)[:300]]}
    if kind=="photos":
        return {"items":[dict(x) for x in progress_photos.entries(conn)[:100]]}
    if kind=="profile":
        return {"items":[dict(x) for x in conn.execute(
            "SELECT key,value FROM profile WHERE key IN "
            "('goal','weight_kg','height_cm','age','sex','resting_hr','sleep_need_h','body_fat_pct_estimate')")]}
    raise HTTPException(status_code=404)

@router.get("/wod-library")
def wod_library(conn=Depends(connection)):
    """Catalogo, risultati e blocchi allenamento collegati: una sola vista coerente."""
    catalog = [dict(row) for row in conn.execute(
        "SELECT id,name,category,description,score_type,custom FROM wods ORDER BY name COLLATE NOCASE"
    ).fetchall()]
    by_id = {row["id"]: {**row, "results": []} for row in catalog}
    results = conn.execute(
        """SELECT wr.id,wr.wod_id,wr.date,wr.score_display,wr.score_value,
                  wr.scaling,wr.notes,wr.is_pr,
                  wk.id AS workout_id,wk.start_time AS workout_start_time,
                  wk.duration_min AS workout_duration_min,wk.rpe AS workout_rpe,
                  wk.load AS workout_load,wk.type AS workout_type,
                  wk.notes AS workout_notes
           FROM wod_results wr LEFT JOIN workouts wk ON wk.wod_result_id=wr.id
           ORDER BY wr.date DESC,wr.id DESC LIMIT 300"""
    ).fetchall()
    for record in results:
        item = dict(record)
        item["blocks"] = (
            workout_details.blocks_for(conn, item["workout_id"])
            if item["workout_id"] is not None else []
        )
        if item["wod_id"] in by_id:
            by_id[item["wod_id"]]["results"].append(item)
    return {"items": list(by_id.values()), "result_limit": 300}

@router.post("/meal",status_code=201)
def create_meal(data:MealBody,conn=Depends(connection)):
    body=data.model_dump(exclude={"request_key"})
    try:
        def insert():
            now=datetime.now(ROME)
            stamp=f"{data.date.isoformat()}T{now:%H:%M:%S.%f}{now:%z}"
            conn.execute("INSERT INTO meals(ts,meal,description,kcal,protein_g,carbs_g,fat_g)"
                         " VALUES(?,?,?,?,?,?,?)",(stamp,data.meal,data.description,
                         data.kcal,data.protein_g,data.carbs_g,data.fat_g))
            return stamp
        return _idempotent(conn,"meal",data.request_key,body,insert)
    except (ValueError,sqlite3.Error) as exc:_bad(exc)

@router.post("/workout",status_code=201)
def create_workout(data:WorkoutBody,conn=Depends(connection)):
    body=data.model_dump(exclude={"request_key"})
    try:
        workout_details.initialize(conn)
        clock=workout_details.start_time_string(data.start_time) if data.start_time is not None else None
        def insert():
            load=workouts.compute_load(conn,data.type,data.duration_min,data.rpe,None)
            cursor=conn.execute(
                "INSERT INTO workouts(date,type,duration_min,avg_hr,max_hr,rpe,load,notes,source,start_time)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (data.date.isoformat(),data.type,data.duration_min,None,None,data.rpe,
                 load,data.notes,"webapp",clock))
            return cursor.lastrowid
        return _idempotent(conn,"workout",data.request_key,body,insert)
    except (ValueError,sqlite3.Error) as exc:_bad(exc)

@router.put("/profile")
def set_profile(data:ProfileBody,conn=Depends(connection)):
    cleaned=data.model_dump(exclude_unset=True,exclude_none=True)
    if not cleaned:
        raise HTTPException(status_code=422,detail="Nessuna impostazione fornita")
    with conn:
        for key,value in cleaned.items():
            conn.execute("INSERT INTO profile(key,value) VALUES(?,?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (key,str(value)))
    return {"saved":True,"fields":sorted(cleaned)}

@router.post("/workout-block",status_code=201)
def add_workout_block(data:BlockBody,conn=Depends(connection)):
    details=data.model_dump(exclude={"workout_id"})
    try:
        identifier=workout_details.append_block(conn,data.workout_id,details)
        return {"id":identifier,"workout_id":data.workout_id,"saved":True}
    except (ValueError,sqlite3.Error) as exc:_bad(exc)

@router.post("/max",status_code=201)
def create_max(data:MaxBody,conn=Depends(connection)):
    try:
        mid=maxes.add_max(conn,data.lift,data.date,data.weight_kg,reps=data.reps,
                          category=data.category,notes=data.notes,source="webapp")
        return {"id":mid,"saved":True}
    except (ValueError,sqlite3.Error) as exc:_bad(exc)

@router.post("/wod",status_code=201)
def create_wod(data:WodBody,conn=Depends(connection)):
    try:
        wid=wods.add_wod(conn,wods.Wod(name=data.name,score_type=data.score_type,
                              description=data.description,custom=1))
        return {"id":wid,"saved":True}
    except (ValueError,sqlite3.Error) as exc:_bad(exc)

@router.post("/result",status_code=201)
def create_result(data:ResultBody,conn=Depends(connection)):
    try:
        return wods.add_result(conn,data.wod_name,data.date.isoformat(),data.score,
                               scaling=data.scaling,notes=data.notes)
    except (ValueError,sqlite3.Error) as exc:_bad(exc)

@router.post("/photo",status_code=201)
def create_photo(data:PhotoBody,conn=Depends(connection)):
    try:
        image=base64.b64decode(data.image_base64,validate=True)
        photo_id=progress_photos.add_photo(conn,db.db_path(),data.taken_on.isoformat(),
                                          data.angle,image,data.notes)
        return {"id":photo_id,"saved":True}
    except (ValueError,sqlite3.Error,binascii.Error) as exc:_bad(exc)

@router.get("/photo/{photo_id}")
def get_photo(photo_id:int,conn=Depends(connection)):
    if photo_id<=0:raise HTTPException(status_code=404,detail="Foto inesistente")
    progress_photos.initialize(conn)
    row=conn.execute("SELECT filename FROM progress_photos WHERE id=?",(photo_id,)).fetchone()
    if not row:raise HTTPException(status_code=404,detail="Foto inesistente")
    try:return Response(progress_photos.photo_bytes(db.db_path(),row["filename"]),
                        media_type="image/jpeg",headers={"Cache-Control":"no-store"})
    except (ValueError,OSError) as exc:raise HTTPException(status_code=404,detail="Foto non disponibile") from exc

@router.get("/day-mode")
def day_mode(day:date,conn=Depends(connection)):
    state=nutrition_schedule.day_mode(conn,day.isoformat())
    return {"date":day.isoformat(),**state}

@router.put("/day-mode")
def set_day_mode(data:ModeBody,conn=Depends(connection)):
    nutrition_schedule.save_mode(conn,data.date.isoformat(),data.mode)
    return {"saved":True,"date":data.date.isoformat(),
            **nutrition_schedule.day_mode(conn,data.date.isoformat())}
