from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_missing_cloud_config_shows_setup_message(monkeypatch):
    monkeypatch.delenv("FINANZE_FILE", raising=False)
    app = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app), default_timeout=30)
    at.secrets["github"] = {"repository": "legacy/repo", "token": "unused"}
    at.secrets["accesso"] = {"password": "test-password"}
    at.run()
    at.text_input(key="_login_password").set_value("test-password")
    at.button[0].click().run()
    assert not at.exception
    assert at.error
    assert "Secrets Google Sheets" in at.error[0].value
