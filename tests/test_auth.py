from pathlib import Path
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_missing_password_blocks_archive(tmp_path, monkeypatch):
    archive = tmp_path / "finanze.xlsx"
    monkeypatch.setenv("FINANZE_FILE", str(archive))
    at = AppTest.from_file(str(APP)).run()
    assert not at.exception
    assert at.error and "Secrets" in at.error[0].value
    assert not at.sidebar.radio
    assert not archive.exists()


def test_login_wrong_password_logout_rotation_and_new_session(tmp_path, monkeypatch):
    archive = tmp_path / "finanze.xlsx"
    monkeypatch.setenv("FINANZE_FILE", str(archive))
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.secrets["accesso"] = {"password": "caffè-test"}
    at.run()
    assert not at.sidebar.radio and not archive.exists()
    at.text_input(key="_login_password").set_value("wrong")
    at.button[0].click().run()
    assert at.error and not archive.exists() and not at.sidebar.radio
    at.text_input(key="_login_password").set_value("caffè-test")
    at.button[0].click().run()
    assert not at.exception and at.sidebar.radio and archive.exists()
    assert "_login_password" not in at.session_state
    at.sidebar.radio[0].set_value("💸 Movimenti").run()
    assert not at.exception and at.sidebar.radio
    next(b for b in at.sidebar.button if b.label == "🔒 Esci").click().run()
    assert not at.sidebar.radio and at.text_input
    at.text_input(key="_login_password").set_value("caffè-test")
    at.button[0].click().run()
    at.secrets["accesso"] = {"password": "changed"}
    at.run()
    assert not at.sidebar.radio and at.text_input
    fresh = AppTest.from_file(str(APP))
    fresh.secrets["accesso"] = {"password": "changed"}
    fresh.run()
    assert not fresh.sidebar.radio
