import streamlit as st

from .. import analytics as stats
from .. import ui
from ..utils import euro


def render(service, snapshot):
    ui.page_header("Statistiche", "Scopri come si muovono i tuoi soldi nel tempo.", service)
    frame = snapshot.movements
    start, end = ui.period_filter(frame, key="statistics")
    selected_account = st.selectbox("Conto da analizzare", [None] + snapshot.account_names(), format_func=lambda value: value if value is not None else "Tutti i conti", key="statistics_account")
    if selected_account:
        frame = frame[frame["Conto"] == selected_account]
    filtered = stats.date_filter(frame, start, end)
    income, expenses, net = stats.totals(filtered)
    ui.metrics([
        ("Entrate", euro(income), "Nel periodo selezionato", "↙", ""),
        ("Uscite", euro(expenses), "Nel periodo selezionato", "↗", "expense"),
        ("Differenza", euro(net, signed=True), "Nel periodo selezionato", "≈", "negative" if net < 0 else ""),
    ])
    left, right = st.columns([1.2, 1])
    with left:
        with st.container(border=True, key="panel_statistics_1"):
            st.subheader("Andamento del saldo")
            st.caption("Il saldo include anche i movimenti precedenti al periodo scelto.")
            ui.balance_chart(stats.balance_history(snapshot, start=start, end=end, account=selected_account), "stats_balance")
    with right:
        with st.container(border=True, key="panel_statistics_2"):
            st.subheader("Entrate e uscite nel tempo")
            ui.flows_chart(stats.monthly_flows(filtered, start, end), "stats_flows")
    left, right = st.columns(2)
    with left:
        with st.container(border=True, key="panel_statistics_3"):
            st.subheader("Spese per categoria")
            ui.donut_chart(stats.grouped_amounts(filtered, kind="Uscita", field="Categoria"), "Categoria", "stats_categories", "Nessuna uscita nel periodo selezionato.")
    with right:
        with st.container(border=True, key="panel_statistics_4"):
            st.subheader("Provenienza delle entrate")
            ui.donut_chart(stats.grouped_amounts(filtered, kind="Entrata", field="Fonte"), "Fonte", "stats_sources", "Nessuna entrata nel periodo selezionato.")
    with st.container(border=True, key="panel_statistics_5"):
        st.subheader("Riepilogo mensile")
        monthly = stats.monthly_flows(filtered, start, end)
        if monthly.empty:
            ui.empty("Aggiungi qualche movimento per costruire il tuo riepilogo.")
        else:
            monthly["Mese"] = monthly["Mese"].apply(lambda value: f"{stats.MONTHS[value.month-1]} {value.year}")
            for column in ("Entrate", "Uscite", "Differenza"):
                monthly[column] = monthly[column].map(euro)
            st.dataframe(monthly, hide_index=True, width="stretch")
