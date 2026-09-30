from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_missing_cloud_config_shows_setup_message(monkeypatch):
    monkeypatch.delenv("FINANZE_FILE", raising=False)
    app = Path(__file__).resolve().parents[1] / "app.py"
    at = AppTest.from_file(str(app), default_timeout=30).run()
    assert not at.exception
    assert at.error
    assert "Secrets" in at.error[0].value
