from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .analytics import MONTHS, account_balances
from .errors import FinanceError
from .service import KINDS
from .utils import euro, new_id, today


GREEN = "#279B82"
CORAL = "#E39A87"
NAVY = "#243F59"
PALETTE = [GREEN, NAVY, "#84B9CE", "#A0A2D2", "#E7B77F", "#91C5B2", CORAL, "#C0CDDA"]


def apply_style():
    css = Path(__file__).with_name("styles.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def navigate(page):
    close_editor()
    st.session_state["page"] = page


def open_editor(kind, record=None):
    st.session_state["_editor"] = {"kind": kind, "record": record, "token": new_id("form")}
    st.rerun()


def close_editor():
    st.session_state.pop("_editor", None)


def render_editor(service):
    editor = st.session_state.get("_editor")
    if not editor:
        return
    if editor["kind"] in ("movement", "match"):
        with st.container(border=True, key="panel_editor"):
            st.button("← Torna indietro", on_click=close_editor, key="editor_back")
            if editor["kind"] == "movement":
                st.subheader("Modifica movimento" if editor["record"] else "Nuovo movimento")
                movement_form(service, token=editor["token"], movement=editor["record"])
            else:
                st.subheader("Modifica partita" if editor["record"] else "Nuova partita")
                match_form(service, token=editor["token"], match=editor["record"])
    elif editor["kind"] == "delete_movement":
        delete_dialog(service, record=editor["record"], kind="movement")
    elif editor["kind"] == "delete_match":
        delete_dialog(service, record=editor["record"], kind="match")


def flash(message):
    close_editor()
    st.session_state["_flash"] = message
    st.rerun()


def show_flash():
    message = st.session_state.pop("_flash", None)
    if message:
        st.success(message)


def page_header(title, subtitle, service, *, match=False, action=True):
    left, right = st.columns([4, 1.35], vertical_alignment="center")
    with left:
        st.markdown(
            f'<div class="eyebrow">LE TUE FINANZE</div><div class="page-title">{escape(title)}</div>'
            f'<div class="page-subtitle">{escape(subtitle)}</div>', unsafe_allow_html=True,
        )
    if action:
        with right:
            with st.container(key="top_action"):
                label = "+ Nuova partita" if match else "+ Nuovo movimento"
                if st.button(label, type="primary", width="stretch", key="top_new"):
                    open_editor("match" if match else "movement")


def hero(balance):
    current = today()
    st.markdown(
        f'<div class="hero"><div class="hero-tag">TOTALE GENERALE</div>'
        f'<div class="hero-label">Patrimonio totale</div><div class="hero-value">{euro(balance)}</div>'
        f'<div class="hero-footer">Tutti i tuoi conti · aggiornato al {current:%d/%m/%Y}</div></div>',
        unsafe_allow_html=True,
    )


def metrics(items):
    cards = []
    for item in items:
        label, value, caption, icon, style = item
        cards.append(
            f'<div class="metric-card {escape(style)}"><div class="metric-top">'
            f'<span class="metric-label">{escape(label)}</span><span class="metric-icon">{escape(icon)}</span></div>'
            f'<div class="metric-value">{escape(str(value))}</div><div class="metric-caption">{escape(caption)}</div></div>'
        )
    st.markdown(f'<div class="metrics" style="--cols:{len(items)}">{"".join(cards)}</div>', unsafe_allow_html=True)


def accounts_overview(snapshot):
    cards = []
    for _, row in account_balances(snapshot).iterrows():
        icon = "◈" if row["Conto"].casefold() == "contanti" else "▣"
        cards.append(
            f'<div class="account"><div class="account-icon">{icon}</div><div>'
            f'<div class="account-name">{escape(row["Conto"])}</div><div class="account-value">{euro(row["Saldo"])}</div></div></div>'
        )
    if cards:
        st.markdown(f'<div class="accounts">{"".join(cards)}</div>', unsafe_allow_html=True)


def empty(message, icon="◌"):
    st.markdown(f'<div class="empty"><div class="empty-icon">{escape(icon)}</div>{escape(message)}</div>', unsafe_allow_html=True)


def chart_style(figure, height=290):
    figure.update_layout(
        height=height, margin=dict(l=10, r=12, t=24, b=22),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", size=12, color="#8190A3"),
        legend=dict(orientation="h", y=1.13, x=0, font=dict(size=11)),
        separators=",.", hoverlabel=dict(bgcolor="#14243b", font_color="white"),
    )
    figure.update_xaxes(showgrid=False, zeroline=False, title=None, tickfont=dict(size=11), automargin=True)
    figure.update_yaxes(gridcolor="#EDF1F5", zeroline=False, title=None, ticksuffix=" €", tickformat=",.0f", tickfont=dict(size=11), automargin=True)
    return figure


def show_chart(figure, key):
    st.plotly_chart(figure, width="stretch", theme=None, config={"displayModeBar": False, "responsive": True}, key=key)


def balance_chart(frame, key):
    if frame.empty:
        empty("Il tuo andamento apparirà dopo il primo movimento.")
        return
    figure = go.Figure(go.Scatter(
        x=frame["Data"], y=frame["Saldo"], mode="lines", line=dict(color=GREEN, width=2.7),
        fill="tozeroy", fillcolor="rgba(39,155,130,.09)", name="Patrimonio",
        hovertemplate="%{x|%d/%m/%Y}<br><b>%{y:,.2f} €</b><extra></extra>",
    ))
    show_chart(chart_style(figure), key)


def flows_chart(frame, key):
    if frame.empty:
        empty("Registra entrate e uscite per vedere il confronto.")
        return
    labels = [f"{MONTHS[value.month-1][:3]} {value.year}" for value in frame["Mese"]]
    figure = go.Figure()
    for field, color in (("Entrate", GREEN), ("Uscite", CORAL)):
        figure.add_trace(go.Bar(x=labels, y=frame[field], name=field, marker_color=color, hovertemplate="%{x}<br>%{y:,.2f} €<extra>%{fullData.name}</extra>"))
    figure.update_layout(barmode="group", bargap=.4, bargroupgap=.13)
    show_chart(chart_style(figure), key)


def donut_chart(frame, field, key, empty_message):
    if frame.empty:
        empty(empty_message)
        return
    figure = go.Figure(go.Pie(
        labels=frame[field], values=frame["Importo"], hole=.72, sort=False,
        marker=dict(colors=PALETTE, line=dict(color="white", width=3)),
        textinfo="none", hovertemplate="%{label}<br><b>%{value:,.2f} €</b><br>%{percent}<extra></extra>",
    ))
    figure = chart_style(figure)
    figure.update_layout(legend=dict(orientation="v", x=1.02, y=.95, font=dict(size=11)), margin=dict(l=0, r=0, t=5, b=5))
    show_chart(figure, key)


def match_chart(frame, key):
    if frame.empty:
        empty("I guadagni appariranno dopo la prima partita.", "⚽")
        return
    labels = [f"{MONTHS[value.month-1][:3]} {value.year}" for value in frame["Mese"]]
    figure = go.Figure(go.Bar(
        x=labels, y=frame["Compenso"], customdata=frame["Partite"], marker_color=GREEN,
        hovertemplate="%{x}<br><b>%{y:,.2f} €</b><br>%{customdata} partite<extra></extra>",
    ))
    figure.update_layout(bargap=.55)
    show_chart(chart_style(figure), key)


def recent_movements(frame):
    if frame.empty:
        empty("Il primo movimento è l'inizio del tuo storico.")
        return
    lines = []
    for _, row in frame.sort_values("Data_creazione", ascending=False).head(6).iterrows():
        outgoing = row["Tipo"] == "Uscita"
        is_transfer = row["Tipo"] == "Giroconto"
        style = "transfer" if is_transfer else ("out" if outgoing else "")
        amount = -row["Importo"] if outgoing else row["Importo"]
        icon = "⇄" if is_transfer else ("↗" if outgoing else "↙")
        account_label = row["Conto"] + (f" → {row['Conto_destinazione']}" if is_transfer else "")
        if row["Arbitraggio_ID"]:
            icon = "⚽"
        lines.append(
            f'<div class="recent"><div class="recent-icon {style}">{icon}</div><div class="recent-detail">'
            f'<div class="recent-title">{escape(row["Descrizione"])}</div><div class="recent-meta">'
            f'{row["Data"]:%d/%m/%Y} · {escape("Giroconto" if is_transfer else (row["Categoria"] or "Senza categoria"))} · {escape(account_label)}</div></div>'
            f'<div class="recent-amount {style}">{euro(amount, signed=not is_transfer)}</div></div>'
        )
    st.markdown("".join(lines), unsafe_allow_html=True)


def period_filter(frame, *, key, column="Data", default="Tutto"):
    with st.expander("Filtra per mese, anno o periodo", expanded=False):
        choices = ["Tutto", "Mese", "Anno", "Periodo"]
        mode = st.radio("Periodo", choices, index=choices.index(default), horizontal=True, key=f"{key}_mode")
        years = sorted(set(frame[column].dt.year.tolist() + [today().year]), reverse=True)
        start = end = None
        if mode == "Mese":
            col1, col2 = st.columns(2)
            year = col1.selectbox("Anno", years, key=f"{key}_month_year")
            month = col2.selectbox("Mese", range(1, 13), index=today().month-1, format_func=lambda value: MONTHS[value-1], key=f"{key}_month")
            start = date(year, month, 1)
            end = (pd.Timestamp(start) + pd.offsets.MonthEnd()).date()
        elif mode == "Anno":
            year = st.selectbox("Anno", years, key=f"{key}_year")
            start, end = date(year, 1, 1), date(year, 12, 31)
        elif mode == "Periodo":
            earliest = frame[column].min().date() if not frame.empty else today().replace(day=1)
            col1, col2 = st.columns(2)
            start = col1.date_input("Dal", value=earliest, format="DD/MM/YYYY", key=f"{key}_start")
            end = col2.date_input("Al", value=today(), format="DD/MM/YYYY", key=f"{key}_end")
            if start > end:
                st.error("La data iniziale deve precedere quella finale.")
                st.stop()
    return start, end


def movement_table(frame, key):
    display = frame.sort_values(["Data", "Data_creazione"], ascending=False).copy()
    transfers = display["_Giroconto"] if "_Giroconto" in display else display["Tipo"] == "Giroconto"
    display["Importo"] = display.apply(lambda row: euro(-row["Importo"] if row["Tipo"] == "Uscita" else row["Importo"], signed=row["Tipo"] != "Giroconto"), axis=1) if not display.empty else pd.Series(dtype=str)
    display["Origine"] = display.apply(lambda row: "⚽ Partita" if row["Arbitraggio_ID"] else ("⇄ Giroconto" if row.get("_Giroconto", row["Tipo"] == "Giroconto") else "Manuale"), axis=1) if not display.empty else pd.Series(dtype=str)
    if not display.empty:
        display.loc[transfers, "Conto"] = display.loc[transfers, "Conto"] + " → " + display.loc[transfers, "Conto_destinazione"]
    display = display[["Data", "Tipo", "Importo", "Categoria", "Descrizione", "Conto", "Fonte", "Note", "Origine"]]
    st.dataframe(display, hide_index=True, width="stretch", column_config={"Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")}, key=key)


def _index(options, value):
    return options.index(value) if value in options else 0


def movement_form(service, *, token, movement=None):
    snapshot = service.snapshot()
    accounts = snapshot.account_names()
    if not accounts:
        st.info("Crea prima un conto nella pagina Gestione.")
        return
    original = movement or {}
    if movement:
        st.caption("Modifica il movimento e salva: il saldo si aggiornerà automaticamente.")
    kind = st.radio("Tipo di movimento", KINDS, index=_index(KINDS, original.get("Tipo", "Uscita")), horizontal=True, key=f"{token}_kind")
    is_transfer = kind == "Giroconto"
    if is_transfer and len(accounts) < 2:
        st.info("Per un giroconto servono almeno due conti. Aggiungi un altro conto in Gestione → Conti.")
        return
    categories = [""] + snapshot.category_names(kind) if not is_transfer else []
    with st.form(f"{token}_form"):
        col1, col2 = st.columns(2)
        amount = col1.number_input("Importo (€)", min_value=0.0, max_value=999999999999.99, value=float(original.get("Importo", 0.0)), step=.01, format="%.2f", key=f"{token}_amount")
        date_value = col2.date_input("Data", value=original.get("Data", today()), max_value=today(), min_value=date(1900, 1, 1), format="DD/MM/YYYY", key=f"{token}_date")
        description = st.text_input("Descrizione (facoltativa)" if is_transfer else "Motivo / descrizione", value=original.get("Descrizione", ""), max_chars=2000, placeholder="Es. prelievo di contanti" if is_transfer else "Es. spesa al supermercato", key=f"{token}_description")
        col1, col2 = st.columns(2)
        destination_account = ""
        if is_transfer:
            account = col1.selectbox("Conto di partenza", accounts, index=_index(accounts, original.get("Conto")), key=f"{token}_account")
            default_destination = original.get("Conto_destinazione") or next(name for name in accounts if name != account)
            destination_account = col2.selectbox("Conto di arrivo", accounts, index=_index(accounts, default_destination), key=f"{token}_destination_account")
            category, source = "", "Giroconto"
        else:
            category = col1.selectbox("Categoria", categories, index=_index(categories, original.get("Categoria", "")), format_func=lambda value: value or "Senza categoria", key=f"{token}_category")
            account = col2.selectbox("Conto", accounts, index=_index(accounts, original.get("Conto")), key=f"{token}_account")
            source = st.text_input("Provenienza / destinazione", value=original.get("Fonte", ""), max_chars=2000, placeholder="Es. datore di lavoro, negozio, persona", key=f"{token}_source")
        notes = st.text_area("Note (facoltative)", value=original.get("Note", ""), max_chars=5000, height=80, key=f"{token}_notes")
        st.caption("Il giroconto sposta soldi tra i tuoi conti: il totale generale e le statistiche di entrate e uscite rimangono invariati." if is_transfer else "Le categorie si personalizzano in Gestione. Per registrare una partita usa Arbitraggio.")
        submitted = st.form_submit_button("Salva modifiche" if movement else ("Salva giroconto" if is_transfer else "Salva movimento"), type="primary", width="stretch")
        if submitted:
            try:
                service.save_movement(kind=kind, amount=amount, date=date_value, description=description, category=category, source=source, account=account, notes=notes, movement_id=original.get("ID"), expected=movement, destination_account=destination_account)
            except FinanceError as exc:
                st.error(str(exc))
            else:
                flash("Giroconto salvato. Saldi dei conti aggiornati." if is_transfer else "Movimento salvato. Saldi e statistiche aggiornati.")


def match_form(service, *, token, match=None):
    snapshot = service.snapshot()
    accounts = snapshot.account_names()
    original = match or {}
    categories = [""] + snapshot.category_names("Entrata")
    default_category = original.get("Categoria", "Arbitraggio" if "Arbitraggio" in categories else "")
    st.caption("Puoi registrare anche partite future. Il compenso entra nel saldo solo quando il pagamento è Ricevuto.")
    statuses = ["Da ricevere", "Ricevuto"]
    status = st.selectbox("Stato pagamento", statuses, index=_index(statuses, original.get("Stato", "Da ricevere")), key=f"{token}_status")
    with st.form(f"{token}_form"):
        col1, col2 = st.columns(2)
        date_value = col1.date_input("Data della partita", value=original.get("Data partita", today()), min_value=date(1900, 1, 1), format="DD/MM/YYYY", key=f"{token}_date")
        package = col2.text_input("Numero pacco", value=original.get("Numero pacco", ""), max_chars=80, placeholder="Es. 0012", key=f"{token}_package")
        col1, col2 = st.columns(2)
        home = col1.text_input("Squadra di casa", value=original.get("Squadra casa", ""), max_chars=120, key=f"{token}_home")
        away = col2.text_input("Squadra ospite", value=original.get("Squadra ospite", ""), max_chars=120, key=f"{token}_away")
        col1, col2 = st.columns(2)
        km = col1.number_input("Km percorsi", min_value=0.0, max_value=999999.0, value=float(original.get("Km", 0.0)), step=1.0, format="%.1f", key=f"{token}_km")
        match_category = col2.text_input("Categoria della partita", value=original.get("Categoria partita", ""), max_chars=120, placeholder="Es. Allievi, Juniores, Promozione", key=f"{token}_match_category")
        fee = st.number_input("Compenso previsto (€)", min_value=0.0, max_value=999999999999.99, value=float(original.get("Compenso", 0.0)), step=.01, format="%.2f", key=f"{token}_fee")
        received_date, account = None, ""
        if status == "Ricevuto":
            col1, col2 = st.columns(2)
            received_date = col1.date_input("Data incasso", value=original.get("Data incasso") or today(), min_value=date(1900, 1, 1), max_value=today(), format="DD/MM/YYYY", key=f"{token}_received")
            account_options = [""] + accounts
            account = col2.selectbox("Accredita sul conto", account_options, index=_index(account_options, original.get("Conto")), format_func=lambda x: x or "Scegli il conto", key=f"{token}_account")
        category = st.selectbox("Categoria dell'entrata", categories, index=_index(categories, default_category), format_func=lambda value: value or "Senza categoria", key=f"{token}_category")
        notes = st.text_area("Note (facoltative)", value=original.get("Note", ""), max_chars=5000, height=80, key=f"{token}_notes")
        if original.get("Stato") == "Ricevuto" and status == "Da ricevere":
            st.warning("Salvando Da ricevere, l'entrata collegata verrà rimossa dal saldo.")
        submitted = st.form_submit_button("Salva modifiche" if match else "Salva partita", type="primary", width="stretch")
        if submitted:
            try:
                service.save_match(date=date_value, package=package, home=home, away=away, fee=fee, account=account, category=category, notes=notes, match_id=original.get("ID"), expected=match, status=status, received_date=received_date, km=km, match_category=match_category)
            except FinanceError as exc:
                st.error(str(exc))
            else:
                flash("Partita salvata. " + ("Incasso aggiornato." if status == "Ricevuto" else "Compenso ancora da ricevere, saldo invariato."))


@st.dialog("Elimina elemento", on_dismiss=close_editor)
def delete_dialog(service, *, record, kind):
    is_match = kind == "match"
    description = f"{record['Squadra casa']} – {record['Squadra ospite']}" if is_match else record["Descrizione"]
    st.write(description)
    if is_match or record.get("Arbitraggio_ID"):
        st.warning("Verranno eliminate la partita e la sua entrata collegata. Il saldo verrà ricalcolato.")
    elif record["Tipo"] == "Giroconto":
        st.write(f"{record['Conto']} → {record['Conto_destinazione']}")
        st.warning("Verrà eliminato il giroconto e saranno ricalcolati i saldi di entrambi i conti.")
    else:
        st.warning("Il movimento verrà eliminato e il saldo ricalcolato.")
    confirmed = st.checkbox("Confermo l'eliminazione", key=f"delete_confirm_{record['ID']}")
    if st.button("Elimina definitivamente", type="primary", disabled=not confirmed, width="stretch"):
        try:
            if is_match:
                service.delete_match(record["ID"], expected=record)
            else:
                service.delete_movement(record["ID"], expected=record)
        except FinanceError as exc:
            st.error(str(exc))
        else:
            flash("Elemento eliminato. Saldi e statistiche aggiornati.")
