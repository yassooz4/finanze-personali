import hashlib

import pandas as pd
import streamlit as st

from ..errors import FinanceError
from ..utils import cents, today

from .. import analytics as stats
from .. import ui
from ..utils import euro


def render(service, snapshot):
    ui.page_header("Arbitraggio", "Le tue partite, i tuoi compensi, un unico storico.", service, match=True)
    frame = snapshot.matches
    start, end = ui.period_filter(frame, key="referee", column="Data partita")
    filtered = stats.date_filter(frame, start, end, column="Data partita")
    selected_status = st.selectbox("Filtra per pagamento", ["Tutti", "Da ricevere", "Ricevuto"], key="referee_status_filter")
    if selected_status != "Tutti":
        filtered = filtered.loc[filtered["Stato"] == selected_status].copy()
    count, earned, average = stats.match_totals(filtered)
    received = sum(cents(v) for v in filtered.loc[filtered["Stato"] == "Ricevuto", "Compenso"]) / 100
    pending = sum(cents(v) for v in filtered.loc[filtered["Stato"] == "Da ricevere", "Compenso"]) / 100
    ui.metrics([
        ("Partite arbitrate", str(count), "Nel periodo selezionato", "⚽", ""),
        ("Compensi totali", euro(earned), "Ricevuti e da ricevere", "€", ""),
        ("Soldi ricevuti", euro(received), "Inclusi nel saldo dei conti", "↙", ""),
        ("Da ricevere", euro(pending), "Ancora da incassare", "◷", ""),
        ("Media per partita", euro(average), "Nel periodo selezionato", "≈", ""),
    ])
    with st.container(border=True, key="panel_referee_1"):
        st.subheader("Compensi per mese di partita")
        st.caption("Compensi delle partite selezionate. Le entrate finanziarie seguono invece la data d’incasso.")
        ui.match_chart(stats.match_monthly(filtered), "referee_monthly")
    with st.container(border=True, key="panel_referee_2"):
        st.subheader("Storico delle partite")
        if filtered.empty:
            ui.empty("Nessuna partita in questo periodo. Registra la prima con + Nuova partita.", "⚽")
        else:
            display = filtered.sort_values("Data partita", ascending=False).copy()
            display["Partita"] = display["Squadra casa"] + " – " + display["Squadra ospite"]
            display["Data incasso"] = display["Data incasso"].dt.date
            display["Data partita"] = display["Data partita"].dt.date
            display = display.set_index("ID")[["Data partita", "Partita", "Numero pacco", "Categoria partita", "Km", "Compenso", "Stato", "Data incasso", "Conto", "Note"]].rename(columns={"Data partita": "Data", "Numero pacco": "N° pacco"})
            records = {row["ID"]: row for row in snapshot.tables["Arbitraggio"]}
            revision = hashlib.sha256(repr(snapshot.tables["Arbitraggio"]).encode()).hexdigest()[:16]
            st.caption("Modifica Stato, Data incasso e Conto nella tabella, poi premi Salva pagamenti. Ricevuto richiede data e conto. Da ricevere rimuove l'eventuale entrata collegata.")
            edited = st.data_editor(display, hide_index=True, width="stretch", num_rows="fixed", disabled=["Data", "Partita", "N° pacco", "Categoria partita", "Km", "Compenso", "Note"], key=f"referee_payments_{revision}", column_config={
                "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                "Km": st.column_config.NumberColumn("Km", format="%.1f"),
                "Categoria partita": st.column_config.TextColumn("Categoria partita"),
                "Compenso": st.column_config.NumberColumn("Compenso", format="%.2f €"),
                "Stato": st.column_config.SelectboxColumn("Stato", options=["Da ricevere", "Ricevuto"], required=True),
                "Data incasso": st.column_config.DateColumn("Data incasso", format="DD/MM/YYYY", max_value=today()),
                "Conto": st.column_config.SelectboxColumn("Conto", options=[""] + snapshot.account_names()),
            })
            if st.button("Salva pagamenti", type="primary", key="save_payments"):
                updates = []
                for match_id, row in edited.iterrows():
                    old = records[match_id]
                    payment_date = None if pd.isna(row["Data incasso"]) else row["Data incasso"]
                    account = row["Conto"] if isinstance(row["Conto"], str) else ""
                    if (row["Stato"], payment_date, account) != (old["Stato"], old["Data incasso"], old["Conto"]):
                        updates.append({"ID": match_id, "Stato": row["Stato"], "Data incasso": payment_date, "Conto": account, "expected": old})
                if not updates:
                    st.info("Nessuna modifica da salvare.")
                else:
                    try:
                        service.update_match_payments(updates)
                    except FinanceError as exc:
                        st.error(str(exc))
                    else:
                        ui.flash("Pagamenti salvati. Saldi e statistiche aggiornati.")
    if filtered.empty:
        return
    with st.expander("Modifica o elimina una partita", expanded=True):
        records = {row["ID"]: row for row in snapshot.tables["Arbitraggio"]}
        ids = filtered.sort_values("Data partita", ascending=False)["ID"].tolist()
        def label(value):
            if value is None:
                return "Seleziona una partita"
            row = records[value]
            return f"{row['Data partita']:%d/%m/%Y} · {row['Squadra casa']} – {row['Squadra ospite']} · {euro(row['Compenso'])}"
        selected = st.selectbox("Partita", [None] + ids, format_func=label, key="selected_match")
        if selected:
            record = records[selected]
            left, right = st.columns(2)
            if left.button("Modifica partita", width="stretch"):
                ui.open_editor("match", record)
            if right.button("Elimina partita", width="stretch"):
                ui.open_editor("delete_match", record)
            st.caption("Modifica ed eliminazione aggiornano l'eventuale entrata già incassata.")
