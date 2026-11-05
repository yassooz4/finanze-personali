import calendar
import json
from copy import deepcopy

import streamlit as st

from .. import ui
from ..assistant import interpret, AssistantError
from ..budget import account_ids, active_plan, budget_summary, proposed_budget, normalize_budget, validate_budget_relations
from ..errors import FinanceError
from ..utils import euro, today


def summary_text(summary):
    return (f"Margine disponibile: **{euro(summary['margine'])}**. "
            f"Hai speso {euro(summary['speso'])}, con {euro(summary['impegni_da_pagare'])} ancora da pagare "
            f"e {euro(summary['riserva'])} di riserva. "
            f"Riferimento per i prossimi {min(7, summary['giorni'])} giorni: {euro(summary['prossimi_7_giorni'])}.")


def render_metrics(snapshot, plan):
    summary = budget_summary(snapshot, plan)
    with st.container(border=True):
        st.subheader("Il tuo piano fino al " + plan["Fine"].strftime("%d/%m/%Y"))
        cols = st.columns(3)
        cols[0].metric("Margine da spendere", euro(summary["margine"]))
        cols[1].metric("Prossimi 7 giorni", euro(summary["prossimi_7_giorni"]))
        cols[2].metric("Spese del periodo", euro(summary["speso"]))
        st.caption(f"Da pagare: {euro(summary['impegni_da_pagare'])} · Riserva: {euro(summary['riserva'])} · {summary['giorni']} giorni rimasti")
        if summary["margine"] < 0:
            st.warning("Il piano supera il budget o i soldi disponibili. Rivedi le spese previste o il limite.")
        if summary["impegni_scaduti"]:
            st.warning("Ci sono impegni scaduti ancora da pagare: restano accantonati nel calcolo.")
        st.caption("Stima basata sui dati registrati. I compensi non incassati sono esclusi. Il riferimento giornaliero è flessibile.")


def _plan_form(service, snapshot, plan):
    day = today()
    plans = snapshot.tables.get("Budget", [])
    labels = {p["ID"]: p["Inizio"].strftime("%d/%m/%Y") + " – " + p["Fine"].strftime("%d/%m/%Y") for p in plans}
    options = [None] + list(labels)
    selected = st.selectbox("Piano da gestire", options, index=options.index(plan["ID"]) if plan else 0,
                            format_func=lambda v: labels.get(v, "Nuovo piano"))
    edit = next((p for p in plans if p["ID"] == selected), None)
    with st.form("budget_form_" + str(selected)):
        start = st.date_input("Inizio del periodo", value=edit["Inizio"] if edit else day.replace(day=1))
        end = st.date_input("Fine del periodo", value=edit["Fine"] if edit else day.replace(day=calendar.monthrange(day.year, day.month)[1]))
        limit = st.number_input("Limite totale del periodo (€)", min_value=0.0, value=float(edit["Limite"]) if edit else 0.0, step=10.0)
        reserve = st.number_input("Riserva da conservare (€)", min_value=0.0, value=float(edit["Riserva"]) if edit else 0.0, step=10.0)
        names = {a["ID"]: a["Nome"] for a in snapshot.accounts}
        accounts = st.multiselect("Conti del budget", list(names), default=account_ids(edit) if edit else list(names), format_func=names.get)
        preferences = st.text_area("Preferenze per i consigli", value=edit["Preferenze"] if edit else "", max_chars=500)
        st.caption("Il limite include tutte le uscite dei conti scelti nel periodo, comprese quelle già registrate. Salva conferma questi valori.")
        if st.form_submit_button("Salva piano", type="primary"):
            try:
                service.save_budget(start=start, end=end, limit=limit, reserve=reserve, accounts=accounts,
                                    preferences=preferences, budget_id=selected, expected=edit)
                st.rerun()
            except FinanceError as exc:
                st.error(str(exc))


def _commitments(service, snapshot, plan):
    if not plan:
        st.info("Crea prima un piano per aggiungere le scadenze.")
        return
    items = [i for i in snapshot.tables["Impegni"] if i["Budget_ID"] == plan["ID"]]
    with st.form("new_commitment"):
        description = st.text_input("Spesa prevista", max_chars=160)
        amount = st.number_input("Importo previsto (€)", min_value=0.01, value=1.0)
        due = st.date_input("Scadenza", value=max(today(), plan["Inizio"]), min_value=plan["Inizio"], max_value=plan["Fine"])
        if st.form_submit_button("Aggiungi impegno"):
            try:
                service.save_commitment(budget_id=plan["ID"], description=description, amount=amount, due=due)
                st.rerun()
            except FinanceError as exc:
                st.error(str(exc))
    names = {a["Nome"] for a in snapshot.accounts if a["ID"] in account_ids(plan)}
    movements = {m["ID"]: m for m in snapshot.tables["Movimenti"] if m["Tipo"] == "Uscita" and m["Conto"] in names and plan["Inizio"] <= m["Data"] <= plan["Fine"]}
    used = {i["Movimento_ID"] for i in snapshot.tables["Impegni"] if i["Movimento_ID"]}
    for item in items:
        with st.expander(f"{item['Descrizione']} · {euro(item['Importo'])} · " + ("Pagato" if item["Movimento_ID"] else "Da pagare")):
            st.caption("Scadenza " + item["Scadenza"].strftime("%d/%m/%Y") + ". Se l'importo effettivo cambia, conta il movimento registrato.")
            choices = [""] + [mid for mid in movements if mid not in used or mid == item["Movimento_ID"]]
            linked = st.selectbox("Collega un'uscita già registrata", choices, index=choices.index(item["Movimento_ID"]),
                format_func=lambda mid: f"{movements[mid]['Data']} · {movements[mid]['Descrizione']} · {euro(movements[mid]['Importo'])}" if mid else "Non pagato / scollega", key="link_" + item["ID"])
            try:
                if st.button("Conferma collegamento", key="pay_" + item["ID"]):
                    service.save_commitment(budget_id=plan["ID"], description=item["Descrizione"], amount=item["Importo"],
                        due=item["Scadenza"], commitment_id=item["ID"], movement_id=linked, expected=item)
                    st.rerun()
                if st.button("Rimuovi impegno", key="remove_" + item["ID"]):
                    service.delete_commitment(item["ID"], expected=item)
                    st.rerun()
            except FinanceError as exc:
                st.error(str(exc))


def _chat(service, snapshot, plan):
    try:
        config = dict(st.secrets.get("groq", {}))
    except FileNotFoundError:
        config = {}
    st.caption("Le risposte AI usano Groq. Inviamo il tuo messaggio, gli ultimi scambi e il riepilogo del budget con categorie e preferenze; non l'intero archivio. La conversazione dura per questa sessione.")
    if not config.get("api_key") or config.get("free_plan_confirmed") is not True:
        st.info("Per attivare la chat configura [groq] nei Secrets con una chiave di un account Free senza fatturazione. Piano e simulatore funzionano già.")
    consent = st.checkbox("Abilita la chat e l'invio dei dati descritti a Groq", key="assistant_consent")
    history = st.session_state.setdefault("assistant_history", [])
    if st.button("Cancella conversazione"):
        st.session_state.pop("assistant_history", None)
        st.session_state.pop("budget_proposal", None)
        st.rerun()
    for item in history:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])
    pending = st.session_state.get("budget_proposal")
    if pending:
        with st.container(border=True):
            st.write("Proposta da confermare: " + euro(pending["limit"]) + " dal " + str(pending["start"]) + " al " + str(pending["end"]))
            selected_names = [a["Nome"] for a in snapshot.accounts if a["ID"] in pending["accounts"]]
            st.caption("Riserva " + euro(pending["reserve"]) + ". Conti: " + ", ".join(selected_names))
            if pending["preferences"]:
                st.text("Preferenze: " + pending["preferences"])
            try:
                if st.button("Conferma nuovo budget", type="primary"):
                    service.save_budget(**pending)
                    st.session_state.pop("budget_proposal", None)
                    history.append({"role": "assistant", "content": "Budget salvato. Il riepilogo è aggiornato."})
                    st.rerun()
            except FinanceError as exc:
                st.error(str(exc))
            if st.button("Annulla proposta"):
                st.session_state.pop("budget_proposal", None)
                st.rerun()
    question = st.chat_input("Chiedimi quanto puoi spendere o imposta il budget", max_chars=2000,
        disabled=not consent or not config.get("api_key") or config.get("free_plan_confirmed") is not True)
    if question:
        st.session_state.pop("budget_proposal", None)
        context = budget_summary(snapshot, plan) if plan else {"budget": "non impostato"}
        try:
            with st.spinner("Consulto il tuo piano…"):
                result = interpret(question, context, history, config)
            intent = result["intent"]
            if intent == "set_budget":
                proposal = proposed_budget(snapshot, result)
                # Validate on a copy before showing a confirmation button.
                draft = deepcopy(snapshot)
                row = {"ID": proposal["budget_id"] or "proposta", "Inizio": proposal["start"], "Fine": proposal["end"],
                       "Limite": proposal["limit"], "Riserva": proposal["reserve"],
                       "Conti_ID": json.dumps(proposal["accounts"]), "Preferenze": proposal["preferences"]}
                normalize_budget("Budget", row)
                draft.tables["Budget"] = [p for p in draft.tables["Budget"] if p["ID"] != row["ID"]] + [row]
                validate_budget_relations(draft.tables)
                st.session_state["budget_proposal"] = proposal
                answer = "Ho preparato la proposta di budget. Controlla i valori e conferma per salvarla."
            elif intent == "simulate":
                if result.get("amount") is None:
                    raise AssistantError("Indica l'importo dell'acquisto da simulare.")
                data = budget_summary(snapshot, plan, purchase=result["amount"])
                answer = f"Dopo una spesa aggiuntiva di **{euro(data['acquisto_simulato'])}**, " + summary_text(data)
                if data["margine"] < 0:
                    answer += " **Questa spesa supera il margine disponibile.**"
            elif intent == "summary":
                answer = summary_text(budget_summary(snapshot, plan))
            else:
                answer = result["answer"]
            history.extend([{"role": "user", "content": question}, {"role": "assistant", "content": answer}])
            st.session_state["assistant_history"] = history[-30:]
            st.rerun()
        except FinanceError as exc:
            st.error(str(exc))


def render(service, snapshot):
    ui.page_header("Assistente", "Un piano concreto per arrivare a fine mese.", service)
    plan = active_plan(snapshot)
    if plan:
        render_metrics(snapshot, plan)
    else:
        st.info("Imposta il tuo primo budget nella scheda Piano. Puoi scegliere anche un periodo fino al prossimo stipendio.")
    chat, simulator, settings, commitments = st.tabs(["Chat", "Simula una spesa", "Piano", "Scadenze"])
    with chat:
        _chat(service, snapshot, plan)
    with simulator:
        if plan:
            purchase = st.number_input("Quanto vorresti spendere? (€)", min_value=0.0, value=0.0, step=5.0)
            data = budget_summary(snapshot, plan, purchase=purchase)
            st.markdown(summary_text(data))
            if data["margine"] < 0:
                st.warning("Questa spesa supera il margine del piano.")
        else:
            st.info("Crea un piano per simulare gli acquisti, anche senza AI.")
    with settings:
        _plan_form(service, snapshot, plan)
    with commitments:
        _commitments(service, snapshot, plan)
