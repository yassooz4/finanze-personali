import pandas as pd
import streamlit as st

from .. import analytics as stats
from .. import ui
from ..utils import euro, today


def render(service, snapshot):
    ui.page_header("Dashboard", "Bentornato. Ecco come stanno le tue finanze.", service)
    current = today()
    month_name = f"{stats.MONTHS[current.month-1]} {current.year}"
    frame = snapshot.movements
    month = stats.date_filter(frame, current.replace(day=1), current)
    income, expenses, net = stats.totals(month)
    left, right = st.columns([1.1, 1.8], gap="medium")
    with left:
        ui.hero(stats.total_balance(snapshot), account_count=len(snapshot.accounts))
    with right:
        st.markdown(f'<div class="section-label month-label">QUESTO MESE <span>{month_name}</span></div>', unsafe_allow_html=True)
        ui.metrics([
            ("Entrate del mese", euro(income), month_name, "↙", ""),
            ("Uscite del mese", euro(expenses), month_name, "↗", "expense"),
            ("Bilancio del mese", euro(net, signed=True), "Entrate meno uscite", "≈", "negative" if net < 0 else ""),
        ])
        ui.month_summary(income, expenses)
    st.markdown('<div class="section-label accounts-label">I TUOI CONTI <span>Il saldo, conto per conto</span></div>', unsafe_allow_html=True)
    ui.accounts_overview(snapshot)
    if frame.empty:
        st.info("Per iniziare, imposta i saldi iniziali in Gestione e registra il tuo primo movimento.")
    left, right = st.columns([1.6, 1], gap="medium")
    with left:
        with st.container(border=True, key="panel_dashboard_2"):
            heading, control = st.columns([1.25, 1], vertical_alignment="center")
            heading.subheader("Andamento del patrimonio")
            period = control.segmented_control("Periodo del grafico", ["1M", "3M", "6M", "1A"], default="6M", selection_mode="single", key="dashboard_period", label_visibility="collapsed")
            months = {"1M": 0, "3M": 2, "6M": 5, "1A": 11}.get(period, 5)
            start = (pd.Timestamp(current.replace(day=1)) - pd.DateOffset(months=months)).date()
            recent_period = stats.date_filter(frame, start, current)
            st.caption("Tutti i conti · include i saldi iniziali")
            ui.balance_chart(stats.balance_history(snapshot, start=start, end=current), "home_balance", height=265)
    with right:
        with st.container(border=True, key="panel_dashboard_3"):
            st.subheader("Dove vanno i tuoi soldi")
            st.caption(month_name)
            expenses_tab, income_tab = st.tabs(["Uscite", "Entrate"])
            with expenses_tab:
                ui.donut_chart(stats.grouped_amounts(month, kind="Uscita", field="Categoria"), "Categoria", "home_categories", "Nessuna spesa registrata questo mese.")
            with income_tab:
                ui.donut_chart(stats.grouped_amounts(month, kind="Entrata", field="Fonte"), "Fonte", "home_sources", "Nessuna entrata registrata questo mese.")
    left, right = st.columns([1.3, 1], gap="medium")
    with left:
        with st.container(border=True, key="panel_dashboard_5"):
            heading, action = st.columns([2, 1], vertical_alignment="center")
            heading.subheader("Ultimi movimenti")
            action.button("Vedi tutti →", width="stretch", on_click=ui.navigate, args=("💸 Movimenti",))
            ui.recent_movements(frame)
    with right:
        with st.container(border=True, key="panel_dashboard_4"):
            st.subheader("Entrate e uscite")
            st.caption("Confronto mensile · segue il periodo del patrimonio")
            ui.flows_chart(stats.monthly_flows(recent_period, start, current), "home_flows")
