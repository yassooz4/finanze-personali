import pandas as pd
import streamlit as st

from .. import analytics as stats
from .. import ui
from ..errors import FinanceError
from ..service import CATEGORY_KINDS
from ..utils import euro
from ..export import excel_export


def _run(operation, message):
    try:
        operation()
    except FinanceError as exc:
        st.error(str(exc))
    else:
        ui.flash(message)


def _accounts(service, snapshot):
    st.subheader("I tuoi conti")
    st.caption("Saldo attuale = saldo iniziale + accrediti − addebiti, giroconti inclusi. Il saldo iniziale è ciò che avevi prima del primo movimento registrato.")
    balances = stats.account_balances(snapshot)
    if not balances.empty:
        display = balances.copy()
        for column in ("Saldo iniziale", "Entrate", "Uscite", "Saldo"):
            display[column] = display[column].map(euro)
        st.dataframe(display.rename(columns={"Entrate": "Accrediti", "Uscite": "Addebiti"}), hide_index=True, width="stretch")
    else:
        st.info("Crea il primo conto per iniziare a registrare i movimenti.")
    with st.expander("+ Aggiungi un conto", expanded=not bool(snapshot.accounts)):
        with st.form("add_account"):
            name = st.text_input("Nome del conto", placeholder="Es. Conto personale", max_chars=80)
            balance = st.number_input("Saldo iniziale (€)", value=0.0, step=.01, format="%.2f")
            if st.form_submit_button("Crea conto", type="primary"):
                _run(lambda: service.save_account(name=name, opening_balance=balance), "Conto creato.")
    if not snapshot.accounts:
        return
    records = {row["ID"]: row for row in snapshot.accounts}
    st.subheader("Rinomina o gestisci un conto")
    st.caption("Scegli il conto, scrivi il nuovo nome e premi Salva conto. La rinomina aggiorna anche movimenti, giroconti e partite.")
    selected = st.selectbox("Conto da rinominare o gestire", [None] + list(records), format_func=lambda value: "Seleziona un conto" if value is None else records[value]["Nome"], key="manage_account")
    if not selected:
        return
    record = records[selected]
    with st.form(f"edit_account_{selected}"):
        left, right = st.columns(2)
        name = left.text_input("Rinomina conto", value=record["Nome"], max_chars=80)
        balance = right.number_input("Modifica saldo iniziale (€)", value=float(record["Saldo_iniziale"]), step=.01, format="%.2f")
        if st.form_submit_button("Salva conto", type="primary"):
            _run(lambda: service.save_account(name=name, opening_balance=balance, account_id=selected, expected=record), "Conto aggiornato e saldi ricalcolati.")
    with st.expander("Elimina questo conto"):
        alternatives = [row["Nome"] for row in snapshot.accounts if row["ID"] != selected]
        used = any(record["Nome"] in (row["Conto"], row["Conto_destinazione"]) for row in snapshot.tables["Movimenti"])
        needs_target = used or record["Saldo_iniziale"] != 0
        if needs_target:
            st.caption("I movimenti e il saldo iniziale verranno riassegnati al conto scelto. Il totale generale rimarrà uguale.")
            if not alternatives:
                st.info("Crea un altro conto a cui riassegnare i dati prima di eliminarlo.")
                return
        with st.form(f"delete_account_{selected}"):
            replacement = st.selectbox("Riassegna al conto", alternatives) if needs_target else None
            confirm = st.checkbox("Confermo l'eliminazione del conto")
            submitted = st.form_submit_button("Elimina conto")
            if submitted:
                if not confirm:
                    st.error("Conferma l'eliminazione con la casella qui sopra.")
                else:
                    _run(lambda: service.delete_account(selected, replacement=replacement, expected=record), "Conto eliminato; storico e totale conservati.")


def _categories(service, snapshot):
    st.subheader("Le tue categorie")
    st.caption("Puoi cambiarle liberamente. Le rinomine si applicano anche allo storico.")
    if snapshot.categories:
        display = pd.DataFrame(snapshot.categories)[["Nome", "Tipo"]].rename(columns={"Tipo": "Disponibile per"})
        st.dataframe(display, hide_index=True, width="stretch")
    with st.expander("+ Aggiungi una categoria", expanded=not bool(snapshot.categories)):
        with st.form("add_category"):
            left, right = st.columns(2)
            name = left.text_input("Nome della categoria", max_chars=80, placeholder="Es. Viaggi")
            kind = right.selectbox("Disponibile per", CATEGORY_KINDS, index=2)
            if st.form_submit_button("Crea categoria", type="primary"):
                _run(lambda: service.save_category(name=name, kind=kind), "Categoria creata.")
    if not snapshot.categories:
        return
    records = {row["ID"]: row for row in snapshot.categories}
    selected = st.selectbox("Categoria da gestire", [None] + list(records), format_func=lambda value: "Seleziona una categoria" if value is None else records[value]["Nome"], key="manage_category")
    if not selected:
        return
    record = records[selected]
    with st.form(f"edit_category_{selected}"):
        left, right = st.columns(2)
        name = left.text_input("Rinomina categoria", value=record["Nome"], max_chars=80)
        kind = right.selectbox("Modifica disponibilità", CATEGORY_KINDS, index=CATEGORY_KINDS.index(record["Tipo"]))
        if st.form_submit_button("Salva categoria", type="primary"):
            _run(lambda: service.save_category(name=name, kind=kind, category_id=selected, expected=record), "Categoria aggiornata, anche nello storico.")
    with st.expander("Elimina questa categoria"):
        st.caption("I movimenti rimangono registrati. Puoi riclassificarli o lasciarli senza categoria.")
        used_kinds = {row["Tipo"] for row in snapshot.tables["Movimenti"] if row["Categoria"] == record["Nome"]}
        alternatives = [row["Nome"] for row in snapshot.categories if row["ID"] != selected and all(row["Tipo"] in (kind, "Entrambe") for kind in used_kinds)]
        with st.form(f"delete_category_{selected}"):
            replacement = st.selectbox("Riclassifica i movimenti", [""] + alternatives, format_func=lambda value: value or "Senza categoria")
            confirm = st.checkbox("Confermo l'eliminazione della categoria")
            if st.form_submit_button("Elimina categoria"):
                if not confirm:
                    st.error("Conferma l'eliminazione con la casella qui sopra.")
                else:
                    _run(lambda: service.delete_category(selected, replacement=replacement, expected=record), "Categoria eliminata; movimenti conservati.")


def _archive(service, snapshot):
    st.subheader("Il tuo archivio")
    if getattr(service.store, "backend", "") == "google_sheets":
        st.write("Tutti i dati sono salvati nel tuo **Google Sheets**. Rimangono nel foglio anche quando Streamlit si riavvia.")
        st.link_button("Apri il foglio Google", service.store.url, width="stretch")
        st.caption("Il download Excel è una copia dei dati attuali. Il database dell'app resta Google Sheets.")
    else:
        st.caption("Modalità di test locale con Excel.")
    st.download_button("Scarica finanze.xlsx", data=excel_export(snapshot.tables), file_name="finanze.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    st.markdown("**Fogli presenti**")
    display = pd.DataFrame([
        {"Foglio": "Movimenti", "Righe": len(snapshot.tables["Movimenti"]), "Contenuto": "Entrate, uscite e giroconti, incluse le entrate delle partite"},
        {"Foglio": "Arbitraggio", "Righe": len(snapshot.tables["Arbitraggio"]), "Contenuto": "Partite e compensi con collegamento al movimento"},
        {"Foglio": "Categorie", "Righe": len(snapshot.categories), "Contenuto": "Categorie e tipi di movimento consentiti"},
        {"Foglio": "Conti", "Righe": len(snapshot.accounts), "Contenuto": "Conti personalizzati e saldi iniziali"},
    ])
    st.dataframe(display, hide_index=True, width="stretch")


def render(service, snapshot):
    ui.page_header("Gestione", "Personalizza i conti e le categorie come preferisci.", service, action=False)
    accounts, categories, archive = st.tabs(["Conti", "Categorie", "Archivio"])
    with accounts:
        _accounts(service, snapshot)
    with categories:
        _categories(service, snapshot)
    with archive:
        _archive(service, snapshot)
