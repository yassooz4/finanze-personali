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


def test_direct_reimbursement_moves_existing_money_without_creating_income(tmp_path):
    service = FinanceService(tmp_path / "finanze.xlsx")
    origin, source = service.snapshot().account_names()
    common = {"date": today(), "category": "", "source": "", "description": "Test rimborso"}
    expense = service.save_movement(
        kind="Uscita", amount=93, account=origin, reimbursable=True, expected_refund=83, **common,
    )
    service.save_movement(kind="Entrata", amount=100, account=source, **common)
    transfer = {
        **common, "kind": "Giroconto", "account": source, "destination_account": origin,
        "refund_expense_id": expense,
    }
    service.save_movement(amount=60, **transfer)
    with pytest.raises(ValidationError):
        service.save_movement(amount=24, **transfer)
    service.save_movement(amount=23, **transfer)

    snapshot = service.snapshot()
    credited, pending = reimbursement_amounts(snapshot.tables["Movimenti"], include_internal=True)
    assert (credited[expense], pending[expense]) == (8300, 0)
    assert account_balances(snapshot).set_index("Conto")["Saldo"].to_dict() == {origin: -10, source: 17}
    assert snapshot.movements["Tipo"].tolist() == ["Uscita", "Entrata", "Giroconto", "Giroconto"]
    net = grouped_amounts(snapshot.movements, kind="Uscita", field="Categoria", snapshot=snapshot)
    assert net["Importo"].tolist() == [93]


def test_refund_panel_registers_direct_transfer(tmp_path):
    from streamlit.testing.v1 import AppTest

    archive = tmp_path / "finanze.xlsx"
    service = FinanceService(archive)
    origin, source = service.snapshot().account_names()
    service.save_movement(
        kind="Uscita", amount=93, account=origin, date=today(), category="",
        source="", description="Spesa anticipata", reimbursable=True, expected_refund=83,
    )
    script = tmp_path / "refund_panel.py"
    script.write_text(
        "from finanze_app.pages.movements import render\n"
        "from finanze_app.service import FinanceService\n"
        f"service = FinanceService({str(archive)!r})\n"
        "render(service, service.snapshot())\n",
        encoding="utf-8",
    )
    app = AppTest.from_file(str(script), default_timeout=30).run()
    assert not app.exception
    button = next(button for button in app.button if button.label == "Salva giroconto")
    button.click().run()
    assert not app.exception
    snapshot = service.snapshot()
    transfer = snapshot.tables["Movimenti"][-1]
    assert (transfer["Tipo"], transfer["Importo"], transfer["Conto"], transfer["Conto_destinazione"]) == (
        "Giroconto", 83, source, origin,
    )
    assert not any(button.label == "Salva giroconto" for button in app.button)
