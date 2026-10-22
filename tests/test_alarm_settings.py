"""Sveglia: revisioni idempotenti, autorizzazioni, conferma Android e UI."""
import json
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient

from benessere import alarm_settings, db
from sync_server import SyncHTTPServer
from webapp.api.main import app


@pytest.fixture
def conn(tmp_path):
    c=db.connect(tmp_path/"alarm.sqlite3")
    yield c
    c.close()


def test_default_is_disabled_and_not_claimed_installed(conn):
    a=alarm_settings.read(conn)
    assert a["enabled"] is False
    assert a["delivery"]=="not_configured"
    assert a["device_ack"] is None
    assert a["strap_control"]=="not_implemented"


def test_save_ack_and_version_guard(conn):
    item={"enabled":True,"deadline":"07:15","weekdays":[1,3,5],
          "window_minutes":30,"mode":"fixed"}
    created=alarm_settings.save(conn,item)
    assert created["revision"]==1
    assert created["delivery"]=="pending_phone"
    again=alarm_settings.save(conn,item)
    assert again["revision"]==1
    ok=alarm_settings.acknowledge(conn,"android_phone_01",1,True)
    assert ok["delivery"]=="confirmed"
    updated=alarm_settings.save(conn,{**item,"deadline":"07:25"})
    assert updated["revision"]==2
    assert updated["delivery"]=="pending_phone"
    with pytest.raises(ValueError,match="superata"):
        alarm_settings.acknowledge(conn,"android_phone_01",1,True)
    failed=alarm_settings.acknowledge(conn,"android_phone_01",2,False,"Permesso sveglie esatte mancante")
    assert failed["delivery"]=="failed"
    assert failed["device_ack"]["installed"]==0


@pytest.mark.parametrize("bad", [
    {"enabled":True,"deadline":"25:00"},
    {"enabled":True,"deadline":"07:01","weekdays":[]},
    {"enabled":True,"deadline":"07:00","weekdays":[1,1]},
    {"enabled":True,"deadline":"07:00","mode":"helio_ble"},
    {"enabled":True,"deadline":"07:00","mode":"smart"},
    {"enabled":True,"deadline":"07:00","window_minutes":10},
    {"enabled":"true","deadline":"07:00"},
])
def test_invalid_config_is_rejected(conn,bad):
    with pytest.raises(ValueError):
        alarm_settings.save(conn,bad)
    assert alarm_settings.read(conn)["revision"]==0


def test_api_requires_token_and_denies_if_not_configured(tmp_path,monkeypatch):
    monkeypatch.setenv("BENESSERE_DB",str(tmp_path/"api.sqlite3"))
    monkeypatch.delenv("BENESSERE_WEB_API_TOKEN",raising=False)
    with TestClient(app) as client:
        assert client.get("/v1/summary").status_code==401
        assert client.get("/v1/alarm",headers={"Authorization":"Bearer insecure"}).status_code==401


def test_api_alarm_update_is_access_controlled(tmp_path,monkeypatch):
    monkeypatch.setenv("BENESSERE_DB",str(tmp_path/"api.sqlite3"))
    token="a"*40
    monkeypatch.setenv("BENESSERE_WEB_API_TOKEN",token)
    head={"Authorization":"Bearer "+token}
    with TestClient(app) as client:
        assert client.get("/health").status_code==200
        assert client.put("/v1/alarm",json={"enabled":True,"deadline":"07:00"}).status_code==401
        first=client.get("/v1/alarm",headers=head)
        assert first.status_code==200 and first.json()["delivery"]=="not_configured"
        saved=client.put("/v1/alarm",headers=head,json={
            "enabled":True,"deadline":"06:45","weekdays":[1,2,3,4,5],
            "window_minutes":30,"mode":"fixed"})
        assert saved.status_code==200
        assert saved.json()["delivery"]=="pending_phone"
        assert saved.json()["strap_control"]=="not_implemented"
        assert client.put("/v1/alarm",headers=head,json={
            "enabled":True,"deadline":"06:45","weekdays":[1],"mode":"smart"}).status_code==422
        assert client.get("/v1/summary",headers=head).status_code==200
        assert client.get("/v1/health-trends",headers=head).status_code==200


def test_existing_android_backend_syncs_alarm_config(tmp_path,monkeypatch):
    import threading
    monkeypatch.setenv("BENESSERE_DB",str(tmp_path/"android.sqlite3"))
    with db.connect() as conn:
        alarm_settings.save(conn,{"enabled":True,"deadline":"07:00",
                                 "window_minutes":30,"weekdays":[1,2,3,4,5],"mode":"fixed"})
    token="long_android_token_"+("x"*40)
    server=SyncHTTPServer(("127.0.0.1",0),token)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        base="http://127.0.0.1:"+str(server.server_port)
        with pytest.raises(HTTPError) as unauth:
            urlopen(base+"/api/v1/alarm-config",timeout=4)
        assert unauth.value.code==401
        req=Request(base+"/api/v1/alarm-config",headers={"Authorization":"Bearer "+token})
        with urlopen(req,timeout=4) as response:
            config=json.load(response)
        assert config["deadline"]=="07:00" and config["revision"]==1
        data=json.dumps({"device_id":"android_phone_01","revision":1,"installed":True}).encode()
        ack=Request(base+"/api/v1/alarm-ack",data=data,method="POST",
                    headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"})
        with urlopen(ack,timeout=4) as response:
            assert json.load(response)["delivery"]=="confirmed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_alarm_streamlit_page_renders(tmp_path,monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("BENESSERE_DB",str(tmp_path/"app.sqlite3"))
    ui=AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"),default_timeout=30)
    ui.run()
    ui.radio(key="nav").set_value("Sveglia").run()
    assert not ui.exception,[str(x.message) for x in ui.exception]
    assert "Sveglia" in ui.radio(key="nav").value
