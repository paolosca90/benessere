"""Smoke test di tutte le viste Streamlit senza toccare dati privati."""
import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize("page", [
    "Panoramica", "Allenamenti", "WOD", "Benchmark",
    "Massimali", "Foto progressi", "Alimentazione", "Impostazioni",
])
def test_pages_render_with_empty_db(tmp_path, monkeypatch, page):
    # Ogni istanza AppTest usa un SQLite effimero, NON la VPS.
    monkeypatch.setenv("BENESSERE_DB", str(tmp_path / f"ui-{page}.sqlite3"))
    path = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(path), default_timeout=20)
    at.run()
    assert not at.exception, [str(x.message) for x in at.exception]
    nav = at.radio(key="nav")
    nav.set_value(page)
    at.run()
    assert not at.exception, [str(x.message) for x in at.exception]
