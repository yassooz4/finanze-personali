import pandas as pd
import streamlit as st

from .. import analytics as stats
from .. import ui
from ..utils import euro, today


def render(service, snapshot):
    ui.page_header("Dashboard", "Una vista chiara dei tuoi soldi.", service)
    ui.hero(stats.total_balance(snapshot))
    current = today()
    month_name = f"{stats.MONTHS[current.month-1]} {current.year}"
    frame = snapshot.movements
    month = stats.date_filter(frame, current.replace(day=1), current)
    income, expenses, net = stats.totals(month)
    ui.metrics([
        ("Entrate del mese", euro(income), month_name, "↙", ""),
        ("Uscite del mese", euro(expenses), month_name, "↗", "expense"),
        ("Differenza entrate − uscite", euro(net, signed=True), month_name, "≈", "negative" if net < 0 else ""),
    ])
    ui.accounts_overview(snapshot)
    if frame.empty:
        st.info("Per iniziare, imposta i saldi iniziali in Gestione e registra il tuo primo movimento.")
    start = (pd.Timestamp(current.replace(day=1)) - pd.DateOffset(months=5)).date()
    recent_period = stats.date_filter(frame, start, current)
    left, right = st.columns([1.2, 1])
    with left:
        with st.container(border=True, key="panel_dashboard_1"):
            st.subheader("Andamento del patrimonio")
            st.caption("Ultimi 6 mesi · include i saldi iniziali")
            ui.balance_chart(stats.balance_history(snapshot, start=start, end=current), "home_balance")
    with right:
        with st.container(border=True, key="panel_dashboard_2"):
            st.subheader("Entrate e uscite")
            st.caption("Confronto mensile · ultimi 6 mesi")
            ui.flows_chart(stats.monthly_flows(recent_period, start, current), "home_flows")
    left, right = st.columns(2)
    with left:
        with st.container(border=True, key="panel_dashboard_3"):
            st.subheader("Spese per categoria")
            st.caption(month_name)
            ui.donut_chart(stats.grouped_amounts(month, kind="Uscita", field="Categoria"), "Categoria", "home_categories", "Nessuna spesa registrata questo mese.")
    with right:
        with st.container(border=True, key="panel_dashboard_4"):
            st.subheader("Da dove arrivano le entrate")
            st.caption(month_name)
            ui.donut_chart(stats.grouped_amounts(month, kind="Entrata", field="Fonte"), "Fonte", "home_sources", "Nessuna entrata registrata questo mese.")
    with st.container(border=True, key="panel_dashboard_5"):
        left, right = st.columns([4, 1])
        left.subheader("Ultimi movimenti registrati")
        right.button("Vedi tutti →", width="stretch", on_click=ui.navigate, args=("💸 Movimenti",))
        ui.recent_movements(frame)
