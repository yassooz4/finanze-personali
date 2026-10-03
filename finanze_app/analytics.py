"""Statistiche derivate dall'Excel. I totali si calcolano in centesimi."""
from __future__ import annotations

from datetime import date

import pandas as pd

from .service import Snapshot
from .utils import cents, today


MONTHS = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]


def date_filter(frame, start=None, end=None, column="Data"):
    result = frame.copy()
    if start is not None:
        result = result[result[column] >= pd.Timestamp(start)]
    if end is not None:
        result = result[result[column] <= pd.Timestamp(end)]
    return result


def totals(frame):
    income = sum(cents(value) for value in frame.loc[frame["Tipo"] == "Entrata", "Importo"])
    expenses = sum(cents(value) for value in frame.loc[frame["Tipo"] == "Uscita", "Importo"])
    return income / 100, expenses / 100, (income - expenses) / 100


def account_movements(frame, account):
    return frame[(frame["Conto"] == account) | (frame["Conto_destinazione"] == account)].copy()


def account_balances(snapshot: Snapshot):
    frame = snapshot.movements
    rows = []
    for account in snapshot.accounts:
        own = account_movements(frame, account["Nome"])
        income, expenses, _ = totals(own)
        transfers = own[own["Tipo"] == "Giroconto"]
        incoming = sum(cents(v) for v in transfers.loc[transfers["Conto_destinazione"] == account["Nome"], "Importo"])
        outgoing = sum(cents(v) for v in transfers.loc[transfers["Conto"] == account["Nome"], "Importo"])
        income = (cents(income) + incoming) / 100
        expenses = (cents(expenses) + outgoing) / 100
        balance = (cents(account["Saldo_iniziale"]) + cents(income) - cents(expenses)) / 100
        rows.append({"Conto": account["Nome"], "Saldo iniziale": account["Saldo_iniziale"], "Entrate": income, "Uscite": expenses, "Saldo": balance})
    return pd.DataFrame(rows, columns=["Conto", "Saldo iniziale", "Entrate", "Uscite", "Saldo"])


def total_balance(snapshot: Snapshot):
    return sum(cents(value) for value in account_balances(snapshot)["Saldo"]) / 100


def monthly_flows(frame, start=None, end=None):
    work = frame[frame["Tipo"] != "Giroconto"].copy()
    if work.empty:
        return pd.DataFrame(columns=["Mese", "Entrate", "Uscite", "Differenza"])
    work["Mese"] = work["Data"].dt.to_period("M").dt.to_timestamp()
    work["Centesimi"] = work["Importo"].map(cents)
    pivot = work.pivot_table(index="Mese", columns="Tipo", values="Centesimi", aggfunc="sum", fill_value=0)
    first = pd.Timestamp(start or work["Data"].min()).replace(day=1)
    last = pd.Timestamp(end or work["Data"].max()).replace(day=1)
    pivot = pivot.reindex(pd.date_range(first, last, freq="MS"), fill_value=0)
    for kind in ("Entrata", "Uscita"):
        if kind not in pivot:
            pivot[kind] = 0
    pivot = pivot[["Entrata", "Uscita"]].rename(columns={"Entrata": "Entrate", "Uscita": "Uscite"}) / 100
    pivot["Differenza"] = (pivot["Entrate"].map(cents) - pivot["Uscite"].map(cents)) / 100
    pivot.index.name = "Mese"
    return pivot.reset_index()


def grouped_amounts(frame, *, kind, field):
    work = frame[frame["Tipo"] == kind].copy()
    if work.empty:
        return pd.DataFrame(columns=[field, "Importo"])
    fallback = "Senza categoria" if field == "Categoria" else "Non specificata"
    work[field] = work[field].replace("", fallback).fillna(fallback)
    work["Centesimi"] = work["Importo"].map(cents)
    result = work.groupby(field, as_index=False)["Centesimi"].sum().rename(columns={"Centesimi": "Importo"})
    result["Importo"] = result["Importo"] / 100
    return result[result["Importo"] > 0].sort_values("Importo", ascending=False)


def balance_history(snapshot: Snapshot, *, start=None, end=None, account=None):
    frame = snapshot.movements
    accounts = snapshot.accounts
    if account:
        frame = account_movements(frame, account)
        accounts = [row for row in accounts if row["Nome"] == account]
    initial = sum(cents(row["Saldo_iniziale"]) for row in accounts)
    if frame.empty:
        return pd.DataFrame({"Data": [pd.Timestamp(start or today()), pd.Timestamp(end or today())], "Saldo": [initial / 100, initial / 100]})
    work = frame.copy()
    def variation(row):
        if row["Tipo"] == "Giroconto":
            if not account:
                return 0
            sign = 1 if row["Conto_destinazione"] == account else -1
        else:
            sign = 1 if row["Tipo"] == "Entrata" else -1
        return cents(row["Importo"]) * sign
    work["Variazione"] = work.apply(variation, axis=1)
    daily = work.groupby("Data")["Variazione"].sum().sort_index()
    # Always accumulate the full history before restricting the chart period.
    first = min(daily.index.min(), pd.Timestamp(start or daily.index.min()))
    last = max(pd.Timestamp(end or today()), daily.index.max())
    index = pd.date_range(first - pd.Timedelta(days=1), last, freq="D")
    balance = daily.reindex(index, fill_value=0).cumsum() + initial
    result = pd.DataFrame({"Data": index, "Saldo": balance.to_numpy() / 100})
    return date_filter(result, start, end)


def match_totals(frame):
    count = len(frame)
    earnings = sum(cents(value) for value in frame["Compenso"]) / 100
    return count, earnings, earnings / count if count else 0.0


def match_monthly(frame):
    if frame.empty:
        return pd.DataFrame(columns=["Mese", "Compenso", "Partite"])
    work = frame.copy()
    work["Mese"] = work["Data partita"].dt.to_period("M").dt.to_timestamp()
    work["Centesimi"] = work["Compenso"].map(cents)
    result = work.groupby("Mese").agg(Compenso=("Centesimi", "sum"), Partite=("ID", "count"))
    result = result.reindex(pd.date_range(result.index.min(), result.index.max(), freq="MS"), fill_value=0)
    result.index.name = "Mese"
    result["Compenso"] = result["Compenso"] / 100
    return result.reset_index()
