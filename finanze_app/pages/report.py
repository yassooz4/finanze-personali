import streamlit as st

from .. import report as reports
from .. import ui
from ..utils import euro


def render(service, snapshot):
    ui.page_header("Report", "Scarica un riepilogo completo con movimenti, entrate, uscite e saldi. Scegli tu periodo e filtri.", service)
    start, end = ui.period_filter(snapshot.movements, key="report")
    with st.container(border=True, key="panel_report_filters"):
        col1, col2, col3 = st.columns(3)
        account = col1.selectbox("Conto", [None] + snapshot.account_names(), format_func=lambda value: value if value is not None else "Tutti i conti", key="report_account")
        kind = col2.selectbox("Tipo", [None] + list(reports.KINDS), format_func=lambda value: value or "Tutti", key="report_kind")
        category_options = [None, ""] + sorted([row["Nome"] for row in snapshot.categories], key=str.casefold)
        category = col3.selectbox("Categoria", category_options, format_func=lambda value: "Tutte" if value is None else (value or "Senza categoria"), key="report_category")
        sections = st.multiselect("Cosa includere nel file Excel", reports.SECTIONS, default=reports.SECTIONS, key="report_sections",
                                  help="Ogni voce diventa un foglio: Riepilogo, Movimenti (con saldo progressivo), Categorie, Mesi, Conti e Arbitraggio.")
    data = reports.build_report(snapshot, start=start, end=end, account=account, kind=kind, category=category)
    values = {label: value for label, value, _ in data.summary}
    ui.metrics([
        ("Entrate", euro(values["Entrate"]), reports.period_label(start, end), "↙", ""),
        ("Uscite", euro(values["Uscite"]), f"{values['Movimenti nel report']} movimenti", "↗", "expense"),
        ("Saldo a fine periodo", euro(values["Saldo a fine periodo"]), f"Inizio: {euro(values['Saldo a inizio periodo'])}", "▣", "negative" if values["Saldo a fine periodo"] < 0 else ""),
        ("Saldo attuale", euro(values["Saldo attuale"]), account or "Tutti i conti", "◈", "negative" if values["Saldo attuale"] < 0 else ""),
    ])
    if data.movements.empty:
        st.info("Nessun movimento corrisponde ai filtri: nel file troverai comunque i saldi del periodo.")
    else:
        with st.expander("Anteprima dei movimenti"):
            st.dataframe(data.movements.sort_values("Data", ascending=False).head(200), hide_index=True, width="stretch",
                         column_config={"Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")})
            if len(data.movements) > 200:
                st.caption("Anteprima limitata agli ultimi 200 movimenti: il file li contiene tutti.")
    with st.container(border=True, key="panel_report_download"):
        st.subheader("Scarica")
        stem = reports.file_stem(start, end)
        left, right = st.columns(2)
        if sections:
            left.download_button("Scarica report Excel", data=reports.to_excel(data, sections), file_name=f"{stem}.xlsx",
                                 mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
        else:
            left.info("Seleziona almeno una voce da includere.")
        right.download_button("Scarica solo movimenti (CSV)", data=reports.to_csv(data), file_name=f"{stem}_movimenti.csv", mime="text/csv", width="stretch")
