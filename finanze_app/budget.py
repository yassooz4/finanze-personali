"""Budget and purchase simulations: all arithmetic uses integer cents."""
from __future__ import annotations

import json
from copy import deepcopy

from .errors import ValidationError
from .utils import as_date, cents, money, new_id, text, today


def account_ids(plan):
    try:
        result = json.loads(plan.get("Conti_ID") or "[]")
    except (ValueError, TypeError):
        raise ValidationError("Conti del budget non validi.") from None
    if not isinstance(result, list) or not result or any(not isinstance(v, str) for v in result) or len(set(result)) != len(result):
        raise ValidationError("Scegli almeno un conto, senza duplicati.")
    return result


def normalize_budget(sheet, row):
    if sheet == "Budget":
        row["Inizio"], row["Fine"] = as_date(row.get("Inizio")), as_date(row.get("Fine"))
        if row["Fine"] < row["Inizio"]:
            raise ValidationError("La fine del budget precede l'inizio.")
        row["Limite"] = money(row.get("Limite"), nonnegative=True)
        row["Riserva"] = money(row.get("Riserva"), nonnegative=True)
        row["Conti_ID"] = json.dumps(account_ids(row))
        row["Preferenze"] = text(row.get("Preferenze"), limit=500)
    else:
        row["Budget_ID"] = text(row.get("Budget_ID"), required=True)
        row["Descrizione"] = text(row.get("Descrizione"), required=True, limit=160)
        row["Importo"] = money(row.get("Importo"), positive=True)
        row["Scadenza"] = as_date(row.get("Scadenza"))
        row["Movimento_ID"] = text(row.get("Movimento_ID"))


def validate_budget_relations(tables):
    plans = tables.get("Budget", [])
    accounts = {a["ID"]: a["Nome"] for a in tables["Conti"]}
    movements = {m["ID"]: m for m in tables["Movimenti"]}
    linked = set()
    for i, plan in enumerate(plans):
        if not set(account_ids(plan)) <= accounts.keys():
            raise ValidationError("Un conto è usato in un budget. Aggiorna prima i conti del budget.")
        if any(plan["Inizio"] <= other["Fine"] and other["Inizio"] <= plan["Fine"] for other in plans[:i]):
            raise ValidationError("I periodi dei budget non possono sovrapporsi.")
    for item in tables.get("Impegni", []):
        plan = next((p for p in plans if p["ID"] == item["Budget_ID"]), None)
        if plan is None or not plan["Inizio"] <= item["Scadenza"] <= plan["Fine"]:
            raise ValidationError("La scadenza dell'impegno deve rientrare nel suo budget.")
        mid = item["Movimento_ID"]
        if not mid:
            continue
        movement = movements.get(mid)
        if (mid in linked or movement is None or movement["Tipo"] != "Uscita"
                or not plan["Inizio"] <= movement["Data"] <= plan["Fine"]
                or movement["Conto"] not in [accounts[a] for a in account_ids(plan)]):
            raise ValidationError("Collega ogni impegno a un'uscita distinta del periodo e dei conti scelti. Scollega l'impegno prima di eliminare o spostare il movimento.")
        linked.add(mid)


def active_plan(snapshot, day=None):
    day = day or today()
    return next((p for p in snapshot.tables.get("Budget", []) if p["Inizio"] <= day <= p["Fine"]), None)


def budget_summary(snapshot, plan=None, *, day=None, purchase=0):
    day = day or today()
    plan = plan or active_plan(snapshot, day)
    if plan is None:
        raise ValidationError("Imposta un budget per il periodo corrente.")
    purchase_cents = cents(money(purchase, nonnegative=True))
    names = {a["Nome"] for a in snapshot.accounts if a["ID"] in account_ids(plan)}
    balance = sum(cents(a["Saldo_iniziale"]) for a in snapshot.accounts if a["Nome"] in names)
    spent = 0
    categories = {}
    for row in snapshot.tables["Movimenti"]:
        if row["Data"] > day:
            continue
        amount = cents(row["Importo"])
        if row["Tipo"] == "Giroconto":
            balance += amount * (int(row["Conto_destinazione"] in names) - int(row["Conto"] in names))
        elif row["Conto"] in names:
            balance += amount if row["Tipo"] == "Entrata" else -amount
            if row["Tipo"] == "Uscita" and plan["Inizio"] <= row["Data"] <= plan["Fine"]:
                spent += amount
                category = row["Categoria"] or "Senza categoria"
                categories[category] = categories.get(category, 0) + amount
    pending = [i for i in snapshot.tables.get("Impegni", []) if i["Budget_ID"] == plan["ID"] and not i["Movimento_ID"]]
    commitments = sum(cents(i["Importo"]) for i in pending)
    remaining = cents(plan["Limite"]) - spent
    cash = balance - cents(plan["Riserva"]) - commitments
    margin = min(remaining - commitments, cash) - purchase_cents
    days = max(0, (plan["Fine"] - max(day, plan["Inizio"])).days + 1)
    return {
        "inizio": plan["Inizio"].isoformat(), "fine": plan["Fine"].isoformat(),
        "limite": plan["Limite"], "riserva": plan["Riserva"], "speso": spent / 100,
        "saldo_conti": balance / 100, "budget_residuo": remaining / 100,
        "impegni_da_pagare": commitments / 100, "impegni_scaduti": sum(i["Scadenza"] < day for i in pending),
        "margine": margin / 100, "acquisto_simulato": purchase_cents / 100,
        "giorni": days, "al_giorno": max(0, margin // days) / 100 if days else 0,
        "prossimi_7_giorni": max(0, margin * min(7, days) // days) / 100 if days else 0,
        "spese_per_categoria": {k: v / 100 for k, v in sorted(categories.items(), key=lambda kv: -kv[1])},
        "arbitraggio_da_ricevere_escluso": sum(cents(m["Compenso"]) for m in snapshot.tables["Arbitraggio"] if m["Stato"] == "Da ricevere") / 100,
        "preferenze": plan["Preferenze"],
    }


class BudgetServiceMixin:
    def save_budget(self, *, start, end, limit, reserve, accounts, preferences="", budget_id=None, expected=None):
        def operation(tables):
            values = {"Inizio": as_date(start), "Fine": as_date(end), "Limite": money(limit, nonnegative=True),
                      "Riserva": money(reserve, nonnegative=True), "Conti_ID": json.dumps(accounts), "Preferenze": preferences}
            if budget_id:
                row = self._get(tables, "Budget", budget_id)
                self._expected(row, expected)
                row.update(values)
            else:
                row = {"ID": new_id("B"), **values}
                tables["Budget"].append(row)
            return row["ID"]
        return self._mutate(operation)

    def save_commitment(self, *, budget_id, description, amount, due, commitment_id=None, movement_id="", expected=None):
        def operation(tables):
            values = {"Budget_ID": budget_id, "Descrizione": description, "Importo": amount,
                      "Scadenza": due, "Movimento_ID": movement_id}
            if commitment_id:
                row = self._get(tables, "Impegni", commitment_id)
                self._expected(row, expected)
                row.update(values)
            else:
                row = {"ID": new_id("I"), **values}
                tables["Impegni"].append(row)
            return row["ID"]
        return self._mutate(operation)

    def delete_commitment(self, commitment_id, *, expected=None):
        def operation(tables):
            row = self._get(tables, "Impegni", commitment_id)
            self._expected(row, expected)
            tables["Impegni"].remove(row)
        self._mutate(operation)


def proposed_budget(snapshot, intent):
    """Build a reviewable proposal, never apply model output directly."""
    current = active_plan(snapshot)
    start, end = as_date(intent.get("start")), as_date(intent.get("end"))
    if not start <= today() <= end:
        raise ValidationError("Dalla chat puoi impostare il periodo corrente. Usa il modulo per altri periodi.")
    mode = intent.get("mode")
    if mode not in ("period_total", "remaining"):
        raise ValidationError("Specifica se l'importo è il limite totale o quello rimasto da oggi.")
    if mode == "remaining":
        start = current["Inizio"] if current else today()
        if current and end != current["Fine"]:
            raise ValidationError("Per cambiare anche la fine del periodo usa il modulo Piano.")
    values = {"start": start, "end": end, "limit": money(intent.get("amount"), nonnegative=True),
              "reserve": current["Riserva"] if current else 0,
              "accounts": account_ids(current) if current else [a["ID"] for a in snapshot.accounts],
              "preferences": current["Preferenze"] if current else "",
              "budget_id": current["ID"] if current else None, "expected": deepcopy(current)}
    if mode == "remaining":
        # Preserve the period/history: remaining spending allowance + already spent.
        names = {a["Nome"] for a in snapshot.accounts if a["ID"] in values["accounts"]}
        spent = sum(cents(m["Importo"]) for m in snapshot.tables["Movimenti"]
                    if m["Tipo"] == "Uscita" and m["Conto"] in names and start <= m["Data"] <= today())
        values["limit"] = (cents(values["limit"]) + spent) / 100
    return values
