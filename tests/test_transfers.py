from datetime import timedelta

import pytest

from finanze_app import analytics as stats
from finanze_app.errors import ConflictError, ValidationError
from finanze_app.service import FinanceService
from finanze_app.utils import today


def transfer(service, **changes):
    values = dict(kind="Giroconto", amount=30, date=today(), description="", category="", source="", account="Conto personale", destination_account="Contanti")
    values.update(changes)
    return service.save_movement(**values)


def opening(service, name, amount):
    account = next(row for row in service.snapshot().accounts if row["Nome"] == name)
    service.save_account(name=name, opening_balance=amount, account_id=account["ID"], expected=account)


def balances(service):
    return stats.account_balances(service.snapshot()).set_index("Conto")["Saldo"].to_dict()


def test_transfer_changes_both_accounts_and_preserves_total_and_statistics(service):
    opening(service, "Conto personale", 100)
    mid = transfer(service)
    restarted = FinanceService(service.store.path)
    snapshot = restarted.snapshot()
    assert balances(restarted) == {"Conto personale": 70, "Contanti": 30}
    assert stats.total_balance(snapshot) == 100
    assert len(snapshot.movements) == 1
    assert snapshot.tables["Movimenti"][0]["ID"] == mid
    assert stats.totals(snapshot.movements) == (0, 0, 0)
    assert stats.monthly_flows(snapshot.movements).empty
    assert stats.grouped_amounts(snapshot.movements, kind="Entrata", field="Fonte").empty
    assert stats.grouped_amounts(snapshot.movements, kind="Uscita", field="Categoria").empty
    assert stats.account_movements(snapshot.movements, "Contanti")["ID"].tolist() == [mid]
    assert set(stats.balance_history(snapshot)["Saldo"]) == {100}
    assert stats.balance_history(snapshot, account="Conto personale").iloc[-1]["Saldo"] == 70
    assert stats.balance_history(snapshot, account="Contanti").iloc[-1]["Saldo"] == 30


def test_transfer_keeps_real_income_expenses_and_history_correct(service):
    opening(service, "Conto personale", 100)
    service.save_movement(kind="Entrata", amount=50, date=today()-timedelta(days=2), description="Lavoro", category="Stipendio", source="Lavoro", account="Conto personale")
    service.save_movement(kind="Uscita", amount=20, date=today()-timedelta(days=1), description="Spesa", category="Cibo", source="Negozio", account="Contanti")
    transfer(service)
    snapshot = service.snapshot()
    assert balances(service) == {"Conto personale": 120, "Contanti": 10}
    assert stats.total_balance(snapshot) == 130
    assert stats.totals(snapshot.movements) == (50, 20, 30)
    flows = stats.monthly_flows(snapshot.movements)
    assert flows["Entrate"].sum() == 50 and flows["Uscite"].sum() == 20
    assert stats.balance_history(snapshot).iloc[-1]["Saldo"] == 130


def test_transfer_edit_reassigns_credit_without_duplicates_and_delete_restores_balances(service):
    opening(service, "Conto personale", 100)
    service.save_account(name="Risparmi", opening_balance=50)
    mid = transfer(service)
    before = service.snapshot().tables["Movimenti"][0]
    transfer(service, amount=20, destination_account="Risparmi", movement_id=mid, expected=before)
    snapshot = service.snapshot()
    assert len(snapshot.movements) == 1
    assert snapshot.tables["Movimenti"][0]["ID"] == mid
    assert snapshot.tables["Movimenti"][0]["Data_creazione"] == before["Data_creazione"]
    assert balances(service) == {"Conto personale": 80, "Contanti": 0, "Risparmi": 70}
    record = snapshot.tables["Movimenti"][0]
    transfer(service, amount=10, account="Risparmi", destination_account="Conto personale", movement_id=mid, expected=record)
    assert balances(service) == {"Conto personale": 110, "Contanti": 0, "Risparmi": 40}
    assert stats.total_balance(service.snapshot()) == 150
    service.delete_movement(mid, expected=service.snapshot().tables["Movimenti"][0])
    assert service.snapshot().movements.empty
    assert balances(service) == {"Conto personale": 100, "Contanti": 0, "Risparmi": 50}


@pytest.mark.parametrize("changes", [
    {"amount": 0}, {"amount": -1}, {"amount": float("nan")}, {"amount": 1.234},
    {"destination_account": "Conto personale"}, {"destination_account": ""},
    {"destination_account": "Sconosciuto"}, {"account": "Sconosciuto"},
    {"date": today() + timedelta(days=1)},
])
def test_invalid_transfer_never_writes_or_changes_balances(service, changes):
    opening(service, "Conto personale", 100)
    before = service.store.path.read_bytes()
    with pytest.raises(ValidationError):
        transfer(service, **changes)
    assert service.store.path.read_bytes() == before
    assert balances(service) == {"Conto personale": 100, "Contanti": 0}


def test_stale_transfer_form_is_rejected(service):
    mid = transfer(service)
    old = service.snapshot().tables["Movimenti"][0]
    transfer(service, amount=20, movement_id=mid, expected=old)
    before = service.store.path.read_bytes()
    with pytest.raises(ConflictError):
        transfer(service, amount=25, movement_id=mid, expected=old)
    with pytest.raises(ConflictError):
        service.delete_movement(mid, expected=old)
    assert service.store.path.read_bytes() == before


def test_account_renames_preserve_transfer_directions_match_links_and_balances(service):
    opening(service, "Conto personale", 100)
    mid = transfer(service)
    service.save_match(date=today(), package="0019", home="A", away="B", fee=45, status="Ricevuto", received_date=today(), account="Contanti", category="Arbitraggio")
    source, target = service.snapshot().accounts
    service.save_account(name="Postepay", opening_balance=source["Saldo_iniziale"], account_id=source["ID"], expected=source)
    service.save_account(name="Portafoglio 💶", opening_balance=target["Saldo_iniziale"], account_id=target["ID"], expected=target)
    snapshot = service.snapshot()
    row = next(row for row in snapshot.tables["Movimenti"] if row["ID"] == mid)
    assert row["Conto"] == "Postepay" and row["Conto_destinazione"] == "Portafoglio 💶"
    assert snapshot.tables["Arbitraggio"][0]["Conto"] == "Portafoglio 💶"
    assert balances(service) == {"Postepay": 70, "Portafoglio 💶": 75}
    assert stats.total_balance(snapshot) == 145
    assert stats.totals(snapshot.movements) == (45, 0, 45)
    for invalid in ("", "postepay"):
        before = service.store.path.read_bytes()
        account = snapshot.accounts[1]
        with pytest.raises(ValidationError):
            service.save_account(name=invalid, opening_balance=0, account_id=account["ID"], expected=account)
        assert service.store.path.read_bytes() == before


def test_account_deletion_cannot_orphan_a_transfer_or_merge_its_two_sides(service):
    opening(service, "Conto personale", 100)
    transfer(service)
    target = service.snapshot().accounts[1]
    before = service.store.path.read_bytes()
    with pytest.raises(ValidationError):
        service.delete_account(target["ID"])
    with pytest.raises(ValidationError, match="giroconti"):
        service.delete_account(target["ID"], replacement="Conto personale")
    assert service.store.path.read_bytes() == before
    service.save_account(name="Risparmi", opening_balance=10)
    service.delete_account(target["ID"], replacement="Risparmi", expected=target)
    assert balances(service) == {"Conto personale": 70, "Risparmi": 40}
    assert stats.total_balance(service.snapshot()) == 110
    assert service.snapshot().tables["Movimenti"][0]["Conto_destinazione"] == "Risparmi"


def test_transfer_can_be_converted_to_and_from_an_ordinary_movement(service):
    opening(service, "Conto personale", 100)
    mid = service.save_movement(kind="Uscita", amount=12, date=today(), description="Spesa", category="Cibo", source="Negozio", account="Conto personale")
    assert stats.total_balance(service.snapshot()) == 88
    transfer(service, movement_id=mid, expected=service.snapshot().tables["Movimenti"][0])
    assert stats.total_balance(service.snapshot()) == 100
    row = service.snapshot().tables["Movimenti"][0]
    assert row["Categoria"] == "" and row["Fonte"] == "Giroconto"
    service.save_movement(kind="Entrata", amount=15, date=today(), description="Rimborso", category="Altro", source="Amico", account="Conto personale", movement_id=mid, expected=row)
    assert balances(service) == {"Conto personale": 115, "Contanti": 0}
    assert len(service.snapshot().movements) == 1
    assert service.snapshot().tables["Movimenti"][0]["Conto_destinazione"] == ""


def test_transfers_use_exact_cents(service):
    opening(service, "Conto personale", .3)
    transfer(service, amount=.1)
    transfer(service, amount=.2)
    assert balances(service) == {"Conto personale": 0, "Contanti": .3}
    assert stats.total_balance(service.snapshot()) == .3


def test_account_movement_view_counts_transfer_sides_without_changing_archive(service):
    opening(service, "Conto personale", 100)
    mid = transfer(service, amount=30.25)
    service.save_movement(kind="Entrata", amount=50, date=today(), description="Lavoro", category="Stipendio", source="", account="Conto personale")
    service.save_movement(kind="Uscita", amount=10, date=today(), description="Spesa", category="Cibo", source="", account="Contanti")
    before = service.store.path.read_bytes()
    frame = service.snapshot().movements
    source = stats.movement_view(frame, "Conto personale")
    destination = stats.movement_view(frame, "Contanti")
    assert stats.totals(source) == (50, 30.25, 19.75)
    assert stats.totals(destination) == (30.25, 10, 20.25)
    assert source.loc[source["ID"] == mid, "Tipo"].iloc[0] == "Uscita"
    assert destination.loc[destination["ID"] == mid, "Tipo"].iloc[0] == "Entrata"
    assert stats.totals(stats.movement_view(frame)) == (50, 10, 40)
    assert frame.loc[frame["ID"] == mid, "Tipo"].iloc[0] == "Giroconto"
    assert service.store.path.read_bytes() == before
    assert len(frame) == 3 and stats.total_balance(service.snapshot()) == 140


def test_account_movement_view_supports_empty_period_and_exact_cents(service):
    transfer(service, amount=.1)
    transfer(service, amount=.2)
    frame = service.snapshot().movements
    assert stats.totals(stats.movement_view(frame, "Conto personale")) == (0, .3, -.3)
    assert stats.totals(stats.movement_view(frame, "Contanti")) == (.3, 0, .3)
    empty = stats.date_filter(frame, start=today() + timedelta(days=1))
    assert stats.totals(stats.movement_view(empty, "Contanti")) == (0, 0, 0)
