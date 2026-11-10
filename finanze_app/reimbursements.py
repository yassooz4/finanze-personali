"""Collegamenti tra spesa anticipata, incassi e giroconti di rimborso."""
from collections import defaultdict

from .errors import ValidationError
from .utils import cents


def validate_reimbursements(movements):
    received = defaultdict(int)
    transferred = defaultdict(int)
    for row in movements.values():
        expected = row["Rimborso_atteso"]
        if expected and (row["Tipo"] != "Uscita" or expected > row["Importo"]):
            raise ValidationError("Il rimborso atteso deve riferirsi a una spesa e non può superarne l'importo.")
        expense_id = row["Spesa_rimborsata_ID"]
        if expense_id:
            expense = movements.get(expense_id)
            if (
                row["Tipo"] != "Entrata" or row["Arbitraggio_ID"]
                or not expense or not expense["Rimborso_atteso"]
                or row["Data"] < expense["Data"]
            ):
                raise ValidationError("Collega l'incasso a una spesa rimborsabile già avvenuta.")
            received[expense_id] += cents(row["Importo"])
            if received[expense_id] > cents(expense["Rimborso_atteso"]):
                raise ValidationError("Gli incassi collegati superano il rimborso atteso.")
        receipt_id = row["Incasso_rimborso_ID"]
        if receipt_id:
            receipt = movements.get(receipt_id)
            expense = movements.get(receipt["Spesa_rimborsata_ID"]) if receipt else None
            if (
                row["Tipo"] != "Giroconto" or not expense
                or row["Conto"] != receipt["Conto"]
                or row["Conto_destinazione"] != expense["Conto"]
                or row["Data"] < receipt["Data"]
            ):
                raise ValidationError("Il giroconto deve seguire l'incasso e riportarlo dal conto di arrivo al conto della spesa.")
            transferred[receipt_id] += cents(row["Importo"])
            if transferred[receipt_id] > cents(receipt["Importo"]):
                raise ValidationError("I giroconti collegati superano il rimborso incassato.")


def reimbursement_amounts(rows):
    """Return received and still-to-transfer cents by original expense ID."""
    expenses = {row["ID"]: row for row in rows if row.get("Rimborso_atteso")}
    received = dict.fromkeys(expenses, 0)
    pending = dict.fromkeys(expenses, 0)
    transfers = defaultdict(int)
    for row in rows:
        if receipt_id := row.get("Incasso_rimborso_ID"):
            transfers[receipt_id] += cents(row["Importo"])
    for row in rows:
        if expense_id := row.get("Spesa_rimborsata_ID"):
            amount = cents(row["Importo"])
            received[expense_id] += amount
            if row["Conto"] != expenses[expense_id]["Conto"]:
                pending[expense_id] += amount - transfers[row["ID"]]
    return received, pending
