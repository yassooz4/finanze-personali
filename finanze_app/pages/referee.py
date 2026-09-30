import streamlit as st

from .. import analytics as stats
from .. import ui
from ..utils import euro


def render(service, snapshot):
    ui.page_header("Arbitraggio", "Le tue partite, i tuoi compensi, un unico storico.", service, match=True)
    frame = snapshot.matches
    start, end = ui.period_filter(frame, key="referee", column="Data partita")
    filtered = stats.date_filter(frame, start, end, column="Data partita")
    count, earned, average = stats.match_totals(filtered)
    ui.metrics([
        ("Partite arbitrate", str(count), "Nel periodo selezionato", "⚽", ""),
        ("Totale guadagnato", euro(earned), "Già incluso nelle tue entrate", "↙", ""),
        ("Media per partita", euro(average), "Nel periodo selezionato", "≈", ""),
    ])
    with st.container(border=True, key="panel_referee_1"):
        st.subheader("Guadagni per mese")
        ui.match_chart(stats.match_monthly(filtered), "referee_monthly")
    with st.container(border=True, key="panel_referee_2"):
        st.subheader("Storico delle partite")
        if filtered.empty:
            ui.empty("Nessuna partita in questo periodo. Registra la prima con + Nuova partita.", "⚽")
        else:
            display = filtered.sort_values("Data partita", ascending=False).copy()
            display["Partita"] = display["Squadra casa"] + " – " + display["Squadra ospite"]
            display["Compenso"] = display["Compenso"].map(euro)
            display = display[["Data partita", "Partita", "Numero pacco", "Compenso", "Conto", "Note"]].rename(columns={"Data partita": "Data", "Numero pacco": "N° pacco"})
            st.dataframe(display, hide_index=True, width="stretch", column_config={"Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")})
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
            st.caption("Modifica ed eliminazione aggiornano automaticamente l'entrata collegata.")
