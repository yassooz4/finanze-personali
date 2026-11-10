import streamlit as st

from .. import analytics as stats
from .. import ui
from ..errors import FinanceError
from ..export import movements_csv, movements_xlsx
from ..service import KINDS
from ..reimbursements import reimbursement_amounts, remaining_transfers
from ..utils import cents, euro, today



def refund_actions(service, snapshot, outstanding):
    movements = snapshot.tables["Movimenti"]
    records = {row["ID"]: row for row in movements}
    remaining = remaining_transfers(movements)
    receipts = {}
    for receipt_id, amount in remaining.items():
        if amount:
            expense_id = records[receipt_id]["Spesa_rimborsata_ID"]
            receipts.setdefault(expense_id, []).append(receipt_id)
    options = [expense_id for expense_id in outstanding if outstanding[expense_id] or receipts.get(expense_id)]
    if not options:
        return

    def label(value):
        row = records[value]
        return f"{row['Data']:%d/%m/%Y} · {row['Descrizione']} · {row['Conto']}"

    with st.expander("Registra rimborso"):
        expense_id = st.selectbox("Spesa da rimborsare", options, format_func=label, key="refund_expense")
        expense = records[expense_id]
        destination = expense["Conto"]
        other_accounts = [account for account in snapshot.account_names() if account != destination]
        actions = []
        if outstanding[expense_id]:
            if other_accounts:
                actions.append("Giroconto con soldi già sul conto")
            actions.append("Registra un incasso esterno")
        if receipts.get(expense_id):
            actions.append("Giroconto di un rimborso già registrato")
        action = st.radio("Cosa vuoi registrare?", actions, key=f"refund_action_{expense_id}")
        incoming = action == "Registra un incasso esterno"
        receipt_id = ""
        account = None
        earliest = expense["Data"]
        maximum = outstanding[expense_id]
        if action == "Giroconto di un rimborso già registrato":
            receipt_id = st.selectbox(
                "Incasso da trasferire", receipts[expense_id],
                format_func=lambda value: f"{label(value)} · {euro(remaining[value] / 100)} da trasferire",
                key=f"refund_receipt_{expense_id}",
            )
            receipt = records[receipt_id]
            account = receipt["Conto"]
            earliest = receipt["Data"]
            maximum = remaining[receipt_id]
        elif incoming:
            account = st.selectbox("Conto su cui è arrivato l’incasso", snapshot.account_names(),
                                   key=f"refund_arrival_{expense_id}")
            st.caption("Usa questa opzione per un incasso che devi ancora registrare nei Movimenti.")
        else:
            account = st.selectbox("Conto da cui prelevare", other_accounts, key=f"refund_source_{expense_id}")

        if not incoming:
            st.caption(f"Giroconto da {account} a {destination}. Registralo dopo aver spostato i soldi.")
        with st.form(f"refund_form_{expense_id}_{action}_{receipt_id}_{maximum}"):
            left, right = st.columns(2)
            amount = left.number_input("Importo del rimborso (€)", min_value=.01, max_value=maximum / 100,
                                       value=maximum / 100, step=.01, format="%.2f")
            date = right.date_input("Data del movimento", value=today(), min_value=earliest,
                                    max_value=today(), format="DD/MM/YYYY")
            if st.form_submit_button("Salva incasso" if incoming else "Salva giroconto", type="primary"):
                try:
                    service.save_movement(
                        kind="Entrata" if incoming else "Giroconto", amount=amount, date=date,
                        description=f"Rimborso · {expense['Descrizione'][:1989]}", category="", source="Rimborso",
                        account=account, destination_account="" if incoming else destination,
                        refund_expense_id="" if receipt_id else expense_id, refund_receipt_id=receipt_id,
                    )
                except FinanceError as exc:
                    st.error(str(exc))
                else:
                    ui.flash("Incasso registrato." if incoming else "Giroconto registrato. Saldi aggiornati.")


def render(service, snapshot):
    ui.page_header("Movimenti", "Registra, cerca e aggiorna entrate, uscite e giroconti.", service)
    frame = snapshot.movements
    start, end = ui.period_filter(frame, key="movements")
    filtered = stats.date_filter(frame, start, end)
    with st.container(border=True, key="panel_movements_1"):
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        search = col1.text_input("Cerca", placeholder="Descrizione, provenienza o note…", key="movement_search")
        kind = col2.selectbox("Tipo", [None] + list(KINDS), format_func=lambda value: value or "Tutti", key="movement_kind_filter")
        account = col3.selectbox("Conto", [None] + snapshot.account_names(), format_func=lambda value: value if value is not None else "Tutti", key="movement_account_filter")
        category_options = [None, ""] + sorted([row["Nome"] for row in snapshot.categories], key=str.casefold)
        category = col4.selectbox("Categoria", category_options, format_func=lambda value: "Tutte" if value is None else (value or "Senza categoria"), key="movement_category_filter")
        reimbursable_only = st.checkbox("Rimborsabili", key="movement_reimbursable_filter")
    if reimbursable_only:
        filtered = filtered[filtered["Rimborso_atteso"] > 0]
    filtered = stats.movement_view(filtered, account)
    if kind == "Giroconto":
        filtered = filtered[filtered["_Giroconto"]]
    elif kind is not None:
        filtered = filtered[filtered["Tipo"] == kind]
    if category is not None:
        filtered = filtered[filtered["Categoria"] == category]
    if search.strip() and not filtered.empty:
        text = filtered[["Descrizione", "Fonte", "Note", "Categoria", "Conto", "Conto_destinazione"]].fillna("").agg(" ".join, axis=1)
        filtered = filtered[text.str.contains(search.strip(), case=False, regex=False)]
    income, expenses, net = stats.totals(filtered)
    balances = stats.account_balances(snapshot)
    balance = stats.total_balance(snapshot) if account is None else float(balances.loc[balances["Conto"] == account, "Saldo"].iloc[0])
    ui.metrics([
        ("Saldo attuale", euro(balance), account or "Tutti i conti · giroconti inclusi nei saldi", "▣", "negative" if balance < 0 else ""),
        ("Entrate", euro(income), "Nei risultati filtrati", "↙", ""),
        ("Uscite", euro(expenses), "Nei risultati filtrati", "↗", "expense"),
        ("Differenza", euro(net, signed=True), f"{len(filtered)} movimenti", "≈", "negative" if net < 0 else ""),
    ])
    st.caption("Il saldo attuale comprende il saldo iniziale e tutti i movimenti, indipendentemente dai filtri. Entrate, uscite e differenza si riferiscono ai risultati filtrati.")
    refunds = filtered[filtered["Rimborso_atteso"] > 0]
    if not refunds.empty:
        received, pending = reimbursement_amounts(snapshot.tables["Movimenti"], include_internal=True)
        outstanding_by_id = {}
        rows = []
        for row in refunds.to_dict("records"):
            expense_id = row["ID"]
            outstanding = cents(row["Rimborso_atteso"]) - received[expense_id]
            outstanding_by_id[expense_id] = outstanding
            to_transfer = pending[expense_id]
            states = []
            if outstanding:
                states.append("Da ricevere")
            if to_transfer:
                states.append("Da trasferire")
            rows.append({
                "Data": row["Data"].strftime("%d/%m/%Y"),
                "Spesa": row["Descrizione"],
                "Conto di partenza": row["Conto"],
                "Stato": " · ".join(states) or "Completato",
                "Da ricevere": outstanding,
                "Da trasferire": to_transfer,
            })
        with st.container(border=True, key="panel_refunds"):
            st.subheader("Rimborsi")
            for column, label in zip(st.columns(2), ("Da ricevere", "Da trasferire")):
                column.metric(label, euro(sum(row[label] for row in rows) / 100))
                for row in rows:
                    row[label] = euro(row[label] / 100)
            st.dataframe(rows, hide_index=True, width="stretch")
            refund_actions(service, snapshot, outstanding_by_id)
    with st.container(border=True, key="panel_movements_2"):
        st.subheader("Storico dei movimenti")
        if filtered.empty:
            ui.empty("Nessun movimento corrisponde ai filtri.")
        else:
            ui.movement_table(filtered, "all_movements")
            st.caption("I giroconti ⇄ sono uscite dal conto di partenza ed entrate nel conto di arrivo." if account is not None else "Le entrate ⚽ provengono dalle partite. Nella vista Tutti, i giroconti ⇄ non sono conteggiati come guadagni o spese: il totale generale rimane invariato.")
    if filtered.empty:
        return
    with st.container(border=True, key="panel_movements_export"):
        st.subheader("Scarica i movimenti")
        st.caption(f"Il file contiene i {len(filtered)} movimenti mostrati con i filtri attuali. Per averli tutti, azzera i filtri.")
        left, right = st.columns(2)
        left.download_button("Scarica CSV", data=movements_csv(filtered), file_name="movimenti.csv", mime="text/csv", width="stretch")
        right.download_button("Scarica Excel", data=movements_xlsx(filtered), file_name="movimenti.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    with st.expander("Modifica o elimina un movimento", expanded=True):
        records = {row["ID"]: row for row in snapshot.tables["Movimenti"]}
        ids = filtered.sort_values(["Data", "Data_creazione"], ascending=False)["ID"].tolist()
        def label(value):
            if value is None:
                return "Seleziona un movimento"
            row = records[value]
            route = f" · {row['Conto']} → {row['Conto_destinazione']}" if row["Tipo"] == "Giroconto" else ""
            return f"{row['Data']:%d/%m/%Y} · {row['Descrizione']}{route} · {euro(row['Importo'])}"
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
