"""App per Streamlit Community Cloud; archivio Excel persistente su GitHub."""
import os
from pathlib import Path

import streamlit as st

from finanze_app import ui
from finanze_app.auth import require_login, logout
from finanze_app.errors import FinanceError, StorageError
from finanze_app.github_storage import cloud_store
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
        config = dict(st.secrets["github"])
    except (FileNotFoundError, KeyError):
        raise StorageError("Configura i Secrets GitHub in Streamlit Cloud. Trovi il modello in secrets.example.toml e i passaggi in README.md.") from None
    if not config.get("repository") or not config.get("token"):
        raise StorageError("Nei Secrets [github] mancano repository o token. Consulta secrets.example.toml.")
    store = cloud_store(repository=config["repository"], token=config["token"], branch=config.get("branch", "dati"), path=config.get("path", "finanze.xlsx"))
    return FinanceService(store.path, store=store)


def main():
    st.set_page_config(page_title="Finanze · v1.1", page_icon="💶", layout="wide", initial_sidebar_state="auto")
    ui.apply_style()
    require_login()
    with st.sidebar:
        st.markdown('<div class="brand"><div class="brand-mark">f</div><div><div class="brand-name">finanze</div><div class="brand-caption">il tuo spazio personale</div></div></div><div class="nav-caption">IL TUO SPAZIO</div>', unsafe_allow_html=True)
        page = st.radio("Navigazione", list(PAGES), label_visibility="collapsed", key="page")
        st.divider()
        st.button("🔒 Esci", on_click=logout, width="stretch")
        if st.button("↻ Aggiorna dati", width="stretch"):
            st.rerun()
        st.markdown('<div class="sidebar-note"><b>Un unico posto per i tuoi soldi</b>Conti, spese e partite.<br>Versione 1.1 · Pagamenti arbitraggio</div>', unsafe_allow_html=True)
    ui.show_flash()
    try:
        service = create_service()
        snapshot = service.snapshot()
        PAGES[page].render(service, snapshot)
        ui.render_editor(service)
    except FinanceError as exc:
        st.error(str(exc))
        st.info("L'archivio non viene azzerato in caso di errore. Controlla la configurazione GitHub e premi Aggiorna dati. I passaggi sono in README.md.")


if __name__ == "__main__":
    main()
