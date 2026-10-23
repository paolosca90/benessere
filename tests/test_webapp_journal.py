"""API journal: read/write sulla stessa copia sqlite, senza dati utente reali."""
from pathlib import Path
import base64
import io
from uuid import uuid4
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from benessere import db
from webapp.api.main import app


@pytest.fixture
def client(tmp_path,monkeypatch):
    path=tmp_path/"benessere.db"
    monkeypatch.setenv("BENESSERE_DB",str(path))
    monkeypatch.setenv("BENESSERE_WEB_API_TOKEN","x"*40)
    with db.connect(path) as conn:
        db.profile_set(conn,"goal","bulk")
    with TestClient(app) as c:
        yield c,{"Authorization":"Bearer "+"x"*40}


def test_journal_protected(client):
    c,token=client
    assert c.get("/v1/journal?kind=meals").status_code==401
    assert c.get("/v1/wod-library").status_code==401
    assert c.post("/v1/meal",json={}).status_code==401
    assert c.get("/v1/photo/1").status_code==401
    assert c.get("/v1/journal?kind=profile",headers=token).status_code==200


def test_meal_idempotence_and_workout_blocks(client):
    c,h=client
    key=str(uuid4())
    body={"request_key":key,"date":"2026-10-22","meal":"breakfast",
          "description":"Crema di riso 75g, whey 30g","kcal":410,
          "protein_g":30,"carbs_g":74,"fat_g":2}
    a=c.post("/v1/meal",json=body,headers=h)
    assert a.status_code==201,a.text
    assert a.json()["saved"]
    b=c.post("/v1/meal",json=body,headers=h)
    assert b.json()["already_exists"]
    body["kcal"]=430
    assert c.post("/v1/meal",json=body,headers=h).status_code==409
    meals=c.get("/v1/journal?kind=meals&day=2026-10-22",headers=h).json()["items"]
    assert len(meals)==1
    workout={"request_key":str(uuid4()),"date":"2026-10-22","type":"tennis",
             "duration_min":90,"rpe":6,"notes":"Tennis 90 minuti"}
    x=c.post("/v1/workout",json=workout,headers=h)
    assert x.status_code==201,x.text
    assert c.post("/v1/workout",json=workout,headers=h).json()["already_exists"]
    items=c.get("/v1/journal?kind=workouts&day=2026-10-22",headers=h).json()["items"]
    assert len(items)==1 and items[0]["type"]=="tennis"
    assert items[0]["blocks"]==[]
    assert c.get("/v1/day-mode?day=2026-10-22",headers=h).json()["mode"]=="tennis"
    assert c.put("/v1/day-mode",json={"date":"2026-10-22","mode":"double"},headers=h).json()["mode"]=="double"


def test_max_wod_result_and_photo(client):
    c,h=client
    result=c.post("/v1/max",json={"lift":"Back Squat","date":"2026-10-22","weight_kg":110,"reps":1},headers=h)
    assert result.status_code==201,result.text
    assert len(c.get("/v1/journal?kind=maxes",headers=h).json()["items"])==1
    wod=c.post("/v1/wod",json={"name":"WOD controllo","score_type":"time"},headers=h)
    assert wod.status_code==201,wod.text
    score=c.post("/v1/result",json={"wod_name":"WOD controllo","date":"2026-10-22","score":"17:00"},headers=h)
    assert score.status_code==201,score.text
    results=c.get("/v1/journal?kind=results",headers=h).json()["items"]
    assert len(results)==1 and results[0]["score_display"]=="17:00"
    image=Image.new("RGB",(16,16),"white")
    out=io.BytesIO();image.save(out,format="PNG")
    photo=c.post("/v1/photo",json={"taken_on":"2026-10-22","angle":"front",
      "image_base64":base64.b64encode(out.getvalue()).decode()},headers=h)
    assert photo.status_code==201,photo.text
    photo_id=photo.json()["id"]
    file=c.get(f"/v1/photo/{photo_id}",headers=h)
    assert file.status_code==200 and file.headers["content-type"]=="image/jpeg"
    assert len(c.get("/v1/journal?kind=photos",headers=h).json()["items"])==1


def test_profile_and_workout_blocks(client):
    c,h=client
    profile=c.put("/v1/profile",json={"goal":"bulk","weight_kg":81.5,
                                      "height_cm":182,"age":36},headers=h)
    assert profile.status_code==200,profile.text
    assert profile.json()["saved"]
    keys={x["key"]:x["value"] for x in c.get("/v1/journal?kind=profile",headers=h).json()["items"]}
    assert keys["weight_kg"]=="81.5"
    assert c.put("/v1/profile",json={"weight_kg":-5},headers=h).status_code==422
    workout=c.post("/v1/workout",json={
        "request_key":str(uuid4()),"date":"2026-10-22",
        "type":"strength","duration_min":55,"rpe":7
    },headers=h)
    assert workout.status_code==201,workout.text
    wid=int(workout.json()["id"])
    block=c.post("/v1/workout-block",json={
        "workout_id":wid,"phase":"wod","label":"WOD C",
        "exercise":"Thrusters","repetitions":30,"weight_kg":45,
        "rpe":7,"time_reference":"unspecified"
    },headers=h)
    assert block.status_code==201,block.text
    rows=c.get("/v1/journal?kind=workouts&day=2026-10-22",headers=h).json()["items"]
    assert len(rows)==1 and len(rows[0]["blocks"])==1
    assert rows[0]["blocks"][0]["rpe"]==7
    assert rows[0]["blocks"][0]["reported_duration_min"] is None


def test_wod_library_returns_full_linked_session(client):
    c,h=client
    wod=c.post("/v1/wod",json={
        "name":"Final 4 Way — Team of 4","score_type":"time",
        "description":"200 TTB, 200 DB Bench Press, 200 Hang DB Snatch, 400 DU, totali team"
    },headers=h)
    assert wod.status_code==201,wod.text
    result=c.post("/v1/result",json={
        "wod_name":"Final 4 Way — Team of 4",
        "date":"2026-10-23","score":"25:40","scaling":"unspecified"
    },headers=h)
    assert result.status_code==201,result.text
    rid=int(result.json()["id"])
    created=c.post("/v1/workout",json={
        "request_key":str(uuid4()),"date":"2026-10-23","type":"other",
        "duration_min":25.6667,"start_time":"09:00","rpe":4,
        "notes":"Squadra da quattro, ripetizioni condivise"
    },headers=h)
    assert created.status_code==201,created.text
    workout_id=int(created.json()["id"])
    with db.connect() as conn:
        from benessere import workout_details
        workout_details.initialize(conn)
        conn.execute("UPDATE workouts SET wod_result_id=? WHERE id=?",(rid,workout_id))
        conn.commit()
    block=c.post("/v1/workout-block",json={
        "workout_id":workout_id,"phase":"wod","label":"Team block 1",
        "exercise":"Toes to Bar","repetitions":200,
        "notes":"Totale squadra, non singolo atleta."
    },headers=h)
    assert block.status_code==201,block.text
    library=c.get("/v1/wod-library",headers=h)
    assert library.status_code==200,library.text
    entry=next(w for w in library.json()["items"] if w["name"]=="Final 4 Way — Team of 4")
    r=entry["results"][0]
    assert r["id"]==rid
    assert r["score_display"]=="25:40"
    assert r["workout_id"]==workout_id
    assert r["workout_rpe"]==4
    assert r["workout_start_time"]=="09:00"
    assert r["blocks"][0]["repetitions"]==200
    assert r["blocks"][0]["exercise"]=="Toes to Bar"


def test_journal_rejects_invalid_data(client):
    c,h=client
    assert c.post("/v1/workout",json={"request_key":str(uuid4()),
        "date":"2026-10-22","type":"tennis","duration_min":-20},headers=h).status_code==422
    assert c.get("/v1/photo/444",headers=h).status_code==404
    assert c.get("/v1/journal?kind=unknown",headers=h).status_code==422
