"""App per Streamlit Community Cloud; archivio persistente su Google Sheets."""
import os
import json
from pathlib import Path

import streamlit as st

from finanze_app import ui
from finanze_app.auth import require_login, logout
from finanze_app.errors import FinanceError, StorageError
from finanze_app.sheets_storage import google_store
from finanze_app.pages import dashboard, movements, referee, settings, statistics
from finanze_app.service import FinanceService


PROJECT_ROOT = Path(__file__).resolve().parent
PAGES = {
    "🏠 Dashboard": dashboard,
    "💸 Movimenti": movements,
    "⚽ Arbitraggio": referee,
    "📊 Statistiche": statistics,
    "⚙️ Gestione": settings,
}


def create_service():
    # Explicit local override exists only for offline development and tests.
    local_file = os.environ.get("FINANZE_FILE")
    if local_file:
        return FinanceService(Path(local_file))
    try:
        config = dict(st.secrets["sheets"])
        credentials = dict(st.secrets["gcp_service_account"])
    except (FileNotFoundError, KeyError):
        raise StorageError("Configura i Secrets Google Sheets: [sheets] e [gcp_service_account]. Trovi il modello in secrets.example.toml e i passaggi in README.md.") from None
    store = google_store(config.get("spreadsheet_id", ""), json.dumps(credentials))
    return FinanceService(None, store=store)



def main():
    st.set_page_config(page_title="Finanze · v2.3", page_icon="💶", layout="wide", initial_sidebar_state="auto")
    ui.apply_style()
    require_login()
    with st.sidebar:
        st.markdown('<div class="brand"><div class="brand-mark">f</div><div><div class="brand-name">finanze</div><div class="brand-caption">il tuo spazio personale</div></div></div><div class="nav-caption">IL TUO SPAZIO</div>', unsafe_allow_html=True)
        page = st.radio("Navigazione", list(PAGES), label_visibility="collapsed", key="page", on_change=ui.close_editor)
        st.divider()
        st.button("🔒 Esci", on_click=logout, width="stretch")
        if st.button("↻ Aggiorna dati", width="stretch"):
            st.rerun()
        st.markdown('<div class="sidebar-note"><b>Un unico posto per i tuoi soldi</b>Conti, spese e partite.<br>Versione 2.3 · Google Sheets · Moduli su pagina</div>', unsafe_allow_html=True)
    ui.show_flash()
    try:
        service = create_service()
        snapshot = service.snapshot()
        if st.session_state.get("_editor", {}).get("kind") not in ("movement", "match"):
            PAGES[page].render(service, snapshot)
        ui.render_editor(service)
    except FinanceError as exc:
        st.error(str(exc))
        st.info("L'archivio non viene azzerato in caso di errore. Controlla la configurazione Google Sheets e premi Aggiorna dati. I passaggi sono in README.md.")


if __name__ == "__main__":
    main()
