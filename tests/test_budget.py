from copy import deepcopy
from datetime import timedelta

import pytest

from finanze_app.budget import active_plan, budget_summary, proposed_budget
from finanze_app.errors import ConflictError, ValidationError
from finanze_app.service import FinanceService
from finanze_app.utils import today


def seed(service, *, limit=500, reserve=100, accounts=None):
    snap = service.snapshot()
    account = snap.accounts[0]
    service.save_account(name=account['Nome'], opening_balance=1000, account_id=account['ID'])
    return service.save_budget(start=today()-timedelta(days=2), end=today()+timedelta(days=7),
        limit=limit, reserve=reserve, accounts=accounts or [a['ID'] for a in snap.accounts])


def spend(service, amount=100, **changes):
    args = dict(kind='Uscita', amount=amount, date=today(), description='Spesa', category='Cibo', source='', account='Conto personale')
    args.update(changes)
    return service.save_movement(**args)


def test_margin_commitment_paid_once_and_restart(service):
    bid = seed(service)
    cid = service.save_commitment(budget_id=bid, description='Bolletta', amount=80, due=today())
    assert budget_summary(service.snapshot())['margine'] == 420
    mid = spend(service, 90)
    # Until explicitly matched, an outstanding bill is still reserved.
    assert budget_summary(service.snapshot())['margine'] == 330
    item = service.snapshot().tables['Impegni'][0]
    service.save_commitment(budget_id=bid, description='Bolletta', amount=80, due=today(), commitment_id=cid, movement_id=mid, expected=item)
    restarted = FinanceService(service.store.path)
    result = budget_summary(restarted.snapshot())
    assert result['margine'] == 410
    assert result['impegni_da_pagare'] == 0
    assert result['speso'] == 90
    assert result['giorni'] == 8


def test_cash_reserve_can_be_more_restrictive_than_limit(service):
    seed(service, limit=2000, reserve=950)
    result = budget_summary(service.snapshot(), purchase=75)
    assert result['margine'] == -25
    assert result['al_giorno'] == 0


def test_transfer_does_not_consume_budget_but_moves_selected_cash(service):
    accounts = service.snapshot().accounts
    seed(service, accounts=[accounts[0]['ID']])
    spend(service, 30, kind='Giroconto', category='', destination_account='Contanti')
    result = budget_summary(service.snapshot())
    assert result['speso'] == 0 and result['saldo_conti'] == 970


def test_unreceived_referee_fee_not_spendable(service):
    seed(service)
    service.save_match(date=today(), package='1', home='A', away='B', fee=200)
    result = budget_summary(service.snapshot())
    assert result['saldo_conti'] == 1000
    assert result['arbitraggio_da_ricevere_escluso'] == 200


def test_overdue_commitment_reserved_and_budget_overspend_visible(service):
    bid = seed(service, limit=100)
    service.save_commitment(budget_id=bid, description='Scaduta', amount=60, due=today()-timedelta(days=1))
    spend(service, 70)
    result = budget_summary(service.snapshot())
    assert result['margine'] == -30 and result['impegni_scaduti'] == 1


def test_no_plan_and_invalid_purchase(service):
    with pytest.raises(ValidationError):
        budget_summary(service.snapshot())
    seed(service)
    for value in (-1, 'nan', True, 1.001):
        with pytest.raises(ValidationError):
            budget_summary(service.snapshot(), purchase=value)


def test_overlap_and_empty_accounts_rejected_without_writes(service):
    seed(service)
    before = service.snapshot().tables
    for accounts in ([], [before['Conti'][0]['ID']]):
        with pytest.raises(ValidationError):
            service.save_budget(start=today(), end=today()+timedelta(days=1), limit=10, reserve=0, accounts=accounts)
    assert service.snapshot().tables == before


def test_duplicate_payment_and_delete_linked_movement_rejected(service):
    bid = seed(service)
    mid = spend(service)
    service.save_commitment(budget_id=bid, description='Uno', amount=100, due=today(), movement_id=mid)
    with pytest.raises(ValidationError):
        service.save_commitment(budget_id=bid, description='Due', amount=100, due=today(), movement_id=mid)
    with pytest.raises(ValidationError):
        service.delete_movement(mid)
    assert len(service.snapshot().movements) == 1


def test_stale_proposal_rejected_and_remaining_preserves_history(service):
    seed(service)
    spend(service, 100)
    original = deepcopy(active_plan(service.snapshot()))
    intent = dict(start=today().isoformat(), end=original['Fine'].isoformat(), mode='remaining', amount=250)
    proposal = proposed_budget(service.snapshot(), intent)
    assert proposal['limit'] == 350 and proposal['start'] == original['Inizio']
    service.save_budget(**proposal)
    assert budget_summary(service.snapshot())['budget_residuo'] == 250
    with pytest.raises(ConflictError):
        service.save_budget(**proposal)


def test_account_rename_preserves_plan_ids(service):
    seed(service)
    account = service.snapshot().accounts[0]
    service.save_account(name='Nuovo', account_id=account['ID'], opening_balance=1000, expected=account)
    assert budget_summary(service.snapshot())['saldo_conti'] == 1000


def test_first_remaining_budget_accounts_for_earlier_spending_today(service):
    spend(service, 25)
    proposal = proposed_budget(service.snapshot(), dict(start=today().isoformat(),
        end=(today()+timedelta(days=7)).isoformat(), mode='remaining', amount=200))
    assert proposal['limit'] == 225


def test_google_migration_and_budget_roundtrip():
    from test_sheets_storage import RemoteSheet, service as remote_service
    remote = RemoteSheet()
    s = remote_service(remote)
    seed(s)
    bid = active_plan(s.snapshot())['ID']
    s.save_commitment(budget_id=bid, description='Bolletta', amount=12.34, due=today())
    fresh = remote_service(remote).snapshot()
    assert budget_summary(fresh)['margine'] == 487.66
    assert remote.grids['Privato'] == [['conservare']]
    assert len(fresh.tables['Budget']) == 1
