import pytest

from finanze_app.analytics import account_balances, grouped_amounts
from finanze_app.errors import ValidationError
from finanze_app.reimbursements import reimbursement_amounts
from finanze_app.service import FinanceService
from finanze_app.utils import today


def test_partial_reimbursement_across_accounts(tmp_path):
    service = FinanceService(tmp_path / "finanze.xlsx")
    origin, arrival = service.snapshot().account_names()

    def save(kind, amount, account, **kwargs):
        return service.save_movement(
            kind=kind, amount=amount, account=account, date=today(),
            category="", source="", description="Test rimborso", **kwargs,
        )

    expense = save("Uscita", 80, origin, reimbursable=True)
    receipt = save("Entrata", 50, arrival, refund_expense_id=expense)
    save("Giroconto", 30, arrival, destination_account=origin, refund_receipt_id=receipt)
    with pytest.raises(ValidationError):
        save("Giroconto", 21, arrival, destination_account=origin, refund_receipt_id=receipt)
    with pytest.raises(ValidationError):
        save("Entrata", 31, origin, refund_expense_id=expense)
    with pytest.raises(ValidationError):
        service.delete_movement(receipt)

    snapshot = service.snapshot()
    received, pending = reimbursement_amounts(snapshot.tables["Movimenti"])
    assert (received[expense], pending[expense]) == (5000, 2000)
    assert account_balances(snapshot).set_index("Conto")["Saldo"].to_dict() == {origin: -50, arrival: 20}
    net = grouped_amounts(snapshot.movements, kind="Uscita", field="Categoria", snapshot=snapshot)
    assert net["Importo"].tolist() == [30]

    save("Entrata", 30, origin, refund_expense_id=expense)
    save("Giroconto", 20, arrival, destination_account=origin, refund_receipt_id=receipt)
    snapshot = service.snapshot()
    received, pending = reimbursement_amounts(snapshot.tables["Movimenti"])
    assert (received[expense], pending[expense]) == (8000, 0)
    assert account_balances(snapshot)["Saldo"].tolist() == [0, 0]
