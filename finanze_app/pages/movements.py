import streamlit as st

from .. import analytics as stats
from .. import ui
from ..utils import euro


def render(service, snapshot):
    ui.page_header("Movimenti", "Registra, cerca e aggiorna le tue entrate e uscite.", service)
    frame = snapshot.movements
    start, end = ui.period_filter(frame, key="movements")
    filtered = stats.date_filter(frame, start, end)
    with st.container(border=True, key="panel_movements_1"):
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        search = col1.text_input("Cerca", placeholder="Descrizione, provenienza o note…", key="movement_search")
        kind = col2.selectbox("Tipo", [None, "Entrata", "Uscita"], format_func=lambda value: value or "Tutti", key="movement_kind_filter")
        account = col3.selectbox("Conto", [None] + snapshot.account_names(), format_func=lambda value: value if value is not None else "Tutti", key="movement_account_filter")
        category_options = [None, ""] + sorted([row["Nome"] for row in snapshot.categories], key=str.casefold)
        category = col4.selectbox("Categoria", category_options, format_func=lambda value: "Tutte" if value is None else (value or "Senza categoria"), key="movement_category_filter")
    if kind is not None:
        filtered = filtered[filtered["Tipo"] == kind]
    if account is not None:
        filtered = filtered[filtered["Conto"] == account]
    if category is not None:
        filtered = filtered[filtered["Categoria"] == category]
    if search.strip() and not filtered.empty:
        text = filtered[["Descrizione", "Fonte", "Note", "Categoria"]].fillna("").agg(" ".join, axis=1)
        filtered = filtered[text.str.contains(search.strip(), case=False, regex=False)]
    income, expenses, net = stats.totals(filtered)
    ui.metrics([
        ("Entrate", euro(income), "Nei risultati filtrati", "↙", ""),
        ("Uscite", euro(expenses), "Nei risultati filtrati", "↗", "expense"),
        ("Differenza", euro(net, signed=True), f"{len(filtered)} movimenti", "≈", "negative" if net < 0 else ""),
    ])
    with st.container(border=True, key="panel_movements_2"):
        st.subheader("Storico dei movimenti")
        if filtered.empty:
            ui.empty("Nessun movimento corrisponde ai filtri.")
        else:
            ui.movement_table(filtered, "all_movements")
            st.caption("Le entrate ⚽ provengono dalle partite e sono già comprese nei saldi.")
    if filtered.empty:
        return
    with st.expander("Modifica o elimina un movimento", expanded=True):
        records = {row["ID"]: row for row in snapshot.tables["Movimenti"]}
        ids = filtered.sort_values(["Data", "Data_creazione"], ascending=False)["ID"].tolist()
        def label(value):
            if value is None:
                return "Seleziona un movimento"
            row = records[value]
            return f"{row['Data']:%d/%m/%Y} · {row['Descrizione']} · {euro(row['Importo'])}"
        selected = st.selectbox("Movimento", [None] + ids, format_func=label, key="selected_movement")
        if selected:
            record = records[selected]
            left, right = st.columns(2)
            if record["Arbitraggio_ID"]:
                left.button("⚽ Modifica in Arbitraggio", width="stretch", on_click=ui.navigate, args=("⚽ Arbitraggio",))
            elif left.button("Modifica movimento", width="stretch"):
                ui.open_editor("movement", record)
            if right.button("Elimina movimento", width="stretch"):
                ui.open_editor("delete_movement", record)
