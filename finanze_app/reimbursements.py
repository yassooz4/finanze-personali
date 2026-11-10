"""Collegamenti tra spesa anticipata, incassi e giroconti di rimborso."""
from collections import defaultdict

from .errors import ValidationError
from .utils import cents


def validate_reimbursements(movements):
    credited = defaultdict(int)
    transferred = defaultdict(int)
    for row in movements.values():
        expected = row["Rimborso_atteso"]
        if expected and (row["Tipo"] != "Uscita" or expected > row["Importo"]):
            raise ValidationError("Il rimborso atteso deve riferirsi a una spesa e non può superarne l'importo.")
        expense_id = row["Spesa_rimborsata_ID"]
        receipt_id = row["Incasso_rimborso_ID"]
        if expense_id:
            expense = movements.get(expense_id)
            if (
                row["Tipo"] not in ("Entrata", "Giroconto") or row["Arbitraggio_ID"]
                or not expense or not expense["Rimborso_atteso"]
                or row["Data"] < expense["Data"]
            ):
                raise ValidationError("Collega il movimento a una spesa rimborsabile già avvenuta.")
            if row["Tipo"] == "Giroconto" and (
                row["Conto_destinazione"] != expense["Conto"] or receipt_id
            ):
                raise ValidationError("Il giroconto diretto deve arrivare sul conto della spesa.")
            credited[expense_id] += cents(row["Importo"])
            if credited[expense_id] > cents(expense["Rimborso_atteso"]):
                raise ValidationError("I rimborsi collegati superano il rimborso atteso.")
        if receipt_id:
            receipt = movements.get(receipt_id)
            expense = movements.get(receipt["Spesa_rimborsata_ID"]) if receipt else None
            if (
                row["Tipo"] != "Giroconto" or not expense or receipt["Tipo"] != "Entrata"
                or row["Conto"] != receipt["Conto"]
                or row["Conto_destinazione"] != expense["Conto"]
                or row["Data"] < receipt["Data"]
            ):
                raise ValidationError("Il giroconto deve seguire l'incasso e riportarlo dal conto di arrivo al conto della spesa.")
            transferred[receipt_id] += cents(row["Importo"])
            if transferred[receipt_id] > cents(receipt["Importo"]):
                raise ValidationError("I giroconti collegati superano il rimborso incassato.")


def remaining_transfers(rows):
    """Return cents still to move for each refund received on another account."""
    accounts = {row["ID"]: row["Conto"] for row in rows if row.get("Rimborso_atteso")}
    remaining = {
        row["ID"]: cents(row["Importo"])
        for row in rows
        if row["Tipo"] == "Entrata" and row.get("Spesa_rimborsata_ID")
        and row["Conto"] != accounts[row["Spesa_rimborsata_ID"]]
    }
    for row in rows:
        if receipt_id := row.get("Incasso_rimborso_ID"):
            remaining[receipt_id] -= cents(row["Importo"])
    return remaining


def reimbursement_amounts(rows, *, include_internal=False):
    """Return credited and still-to-transfer cents by original expense ID."""
    received = {row["ID"]: 0 for row in rows if row.get("Rimborso_atteso")}
    pending = dict.fromkeys(received, 0)
    remaining = remaining_transfers(rows)
    for row in rows:
        if expense_id := row.get("Spesa_rimborsata_ID"):
            if row["Tipo"] == "Entrata" or include_internal:
                received[expense_id] += cents(row["Importo"])
            pending[expense_id] += remaining.get(row["ID"], 0)
    return received, pending
