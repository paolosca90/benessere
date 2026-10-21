"""Photo privacy, monthly max dates, complex classification and profile bridge."""
from io import BytesIO
from pathlib import Path
import pytest
from PIL import Image
from benessere import db, maxes, progress_photos
from sheets_bridge import apply_event


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "benessere.db")
    yield c
    c.close()


def test_month_only_and_power_clean(conn):
    x = apply_event(conn,"aug2026_power_clean","max",{
        "date":"2026-08","lift":"Power Clean","weight_kg":100,"reps":1,"category":"lift"})
    assert x["status"] == "saved"
    assert maxes.history(conn)[0]["date"]=="2026-08"
    assert "giorno non noto" in maxes.readable_date("2026-08")
    assert apply_event(conn,"aug2026_power_clean","max",{
        "date":"2026-08","lift":"Power Clean","weight_kg":100,"reps":1,"category":"lift"})["status"]=="duplicate"


def test_complexes_are_not_1rm(conn):
    apply_event(conn,"aug2026_complex","max",{
        "date":"2026-08","lift":"Power Clean + Hang Squat Clean + Squat Clean & Jerk",
        "weight_kg":80,"category":"complex"})
    assert maxes.best_by_lift(conn)==[]
    assert len(maxes.best_complexes(conn))==1
    assert maxes.best_complexes(conn)[0]["weight_kg"]==80


def test_profile_bridge_minimal_fields(conn):
    data={"height_cm":180,"weight_kg":81,"body_fat_pct_estimate":6}
    assert apply_event(conn,"profile_20261021","profile",data)["status"]=="saved"
    assert apply_event(conn,"profile_20261021","profile",data)["status"]=="duplicate"
    assert conn.execute("SELECT value FROM profile WHERE key='weight_kg'").fetchone()["value"]=="81.0"


def test_progress_photo_private_storage_and_exif_strip(conn,tmp_path):
    img=Image.new("RGB",(100,150),color="blue")
    exif=Image.Exif()
    exif[274]=6
    exif[270]="sample private test"
    output=BytesIO()
    img.save(output,format="JPEG",exif=exif)
    db_file=tmp_path/"benessere.db"
    pid=progress_photos.add_photo(conn,db_file,"2026-10-21","front",output.getvalue(),"foto prova")
    photos=progress_photos.entries(conn)
    assert len(photos)==1 and photos[0]["id"]==pid
    stored=progress_photos.photo_bytes(db_file,photos[0]["filename"])
    with Image.open(BytesIO(stored)) as cleaned:
        assert not cleaned.getexif()
    assert progress_photos.remove_photo(conn,db_file,pid)
    assert not progress_photos.entries(conn)
    with pytest.raises(ValueError):
        progress_photos.add_photo(conn,db_file,"2026-10-21","front",b"not a photo")
