"""Benessere 2.0: API per PWA, separata dai processi Streamlit e Android.

Solo rete interna Docker o reverse proxy autenticato. Il token API NON va mai
inserito nel browser: Next.js lo usa esclusivamente lato server.
"""
from __future__ import annotations
import hmac
import os
from datetime import date
from pathlib import Path
import sys
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict

# Supporta 'uvicorn webapp.api.main:app' dalla radice della repository.
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from benessere import alarm_settings, db, health_metrics, nutrition, nutrition_schedule

app=FastAPI(title="Benessere API",version="2.0.0",docs_url=None,redoc_url=None,openapi_url=None)

def auth(authorization: Annotated[str|None,Header()]=None):
    expected=os.environ.get("BENESSERE_WEB_API_TOKEN","")
    if len(expected)<32 or not authorization or not hmac.compare_digest(authorization,"Bearer "+expected):
        raise HTTPException(status_code=401,detail="Accesso negato")

def connection():
    c=db.connect()
    try:yield c
    finally:c.close()

@app.get("/health")
def health():
    return {"status":"ok","service":"benessere-api-v2"}

@app.get("/v1/summary",dependencies=[Depends(auth)])
def summary(day: date|None=None, conn=Depends(connection)):
    day=day or date.today()
    key=day.isoformat()
    health=health_metrics.snapshot(conn,day,7)
    food=nutrition.day_totals(conn,key)
    activity=conn.execute("SELECT id,type,duration_min,start_time,rpe FROM workouts WHERE date=? ORDER BY id",(key,)).fetchall()
    goal=nutrition_schedule.provisional_bulk_target(conn,key)
    return {"date":key,"health":{"sleep":health["sleep_today"],"heart":health["last_heart"],
          "steps":health["today"]["steps"] if health["today"] else None,
          "hrv":health["hrv_today"],"sync":health["sync"]},
          "nutrition":{"consumed":food,"target":goal},
          "workouts":[dict(x) for x in activity],
          "alarm":{"delivery":alarm_settings.read(conn)["delivery"]}}

@app.get("/v1/health-trends",dependencies=[Depends(auth)])
def trends(days:int=Query(default=30,ge=1,le=90),conn=Depends(connection)):
    return health_metrics.snapshot(conn,date.today(),days)

@app.get("/v1/strength",dependencies=[Depends(auth)])
def strength(conn=Depends(connection)):
    return {"maxes":[dict(x) for x in conn.execute(
        "SELECT * FROM strength_maxes ORDER BY date DESC,id DESC LIMIT 100").fetchall()]}

@app.get("/v1/alarm",dependencies=[Depends(auth)])
def get_alarm(conn=Depends(connection)):
    return alarm_settings.read(conn)

class AlarmBody(BaseModel):
    model_config=ConfigDict(extra="forbid")
    enabled:bool=False
    deadline:str="07:00"
    window_minutes:int=Field(default=30,ge=15,le=60)
    weekdays:list[int]=Field(default_factory=lambda:list(range(1,8)))
    mode:str="fixed"

@app.put("/v1/alarm",dependencies=[Depends(auth)])
def put_alarm(payload:AlarmBody,conn=Depends(connection)):
    try:return alarm_settings.save(conn,payload.model_dump())
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc))
