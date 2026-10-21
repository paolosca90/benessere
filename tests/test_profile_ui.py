"""Profilo con dati reali, modulo di salvataggio e campi opzionali."""
from pathlib import Path

from streamlit.testing.v1 import AppTest
from benessere import db

APP=Path(__file__).resolve().parents[1]/"app.py"


def run_profile(tmp_path, monkeypatch, values):
    path=tmp_path/"profile.sqlite3"
    monkeypatch.setenv("BENESSERE_DB",str(path))
    c=db.connect(path)
    for key,value in values.items():
        db.profile_set(c,key,str(value))
    c.close()
    app=AppTest.from_file(str(APP),default_timeout=30)
    app.run()
    app.radio(key="nav").set_value("Impostazioni").run()
    return app,path


def test_profile_with_existing_real_measurements(tmp_path,monkeypatch):
    app,_=run_profile(tmp_path,monkeypatch,{"height_cm":180,"weight_kg":81,"body_fat_pct_estimate":6})
    assert not app.exception,[str(e.message) for e in app.exception]


def test_profile_with_all_saved_fields(tmp_path,monkeypatch):
    app,_=run_profile(tmp_path,monkeypatch,{
        "sex":"m","age":35,"height_cm":180,"weight_kg":81,"goal":"maintain",
        "resting_hr":55,"body_fat_pct_estimate":6,"sleep_need_h":8
    })
    assert not app.exception,[str(e.message) for e in app.exception]


def test_profile_save_changes_existing_fields(tmp_path,monkeypatch):
    app,path=run_profile(tmp_path,monkeypatch,{
        "sex":"m","age":35,"height_cm":180,"weight_kg":81,"goal":"maintain",
        "body_fat_pct_estimate":6
    })
    assert not app.exception,[str(e.message) for e in app.exception]
    values=app.number_input
    # Trova il peso senza usare il posizionamento grafico (mobile/desktop).
    weight=next((x for x in values if x.label=="Peso corporeo (kg)"),None)
    assert weight is not None
    weight.set_value(82.5)
    next(x for x in app.button if x.label=="Salva profilo").click().run()
    assert not app.exception,[str(e.message) for e in app.exception]
    c=db.connect(path)
    assert db.profile_get_float(c,"weight_kg")==82.5
    c.close()
