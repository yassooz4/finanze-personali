from datetime import timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from finanze_app.analytics import total_balance
from finanze_app.service import FinanceService
from finanze_app.utils import today


APP = Path(__file__).resolve().parents[1] / "app.py"


def widget(elements, label):
    return next(element for element in elements if element.label == label)


@pytest.fixture
def app(tmp_path, monkeypatch):
    path = tmp_path / "finanze.xlsx"
    monkeypatch.setenv("FINANZE_FILE", str(path))
    app_test = AppTest.from_file(str(APP), default_timeout=30)
    app_test.secrets["accesso"] = {"password": "test-password"}
    app_test.run()
    app_test.text_input(key="_login_password").set_value("test-password")
    app_test.button[0].click().run()
    assert not app_test.exception
    return app_test, FinanceService(path)


def test_every_empty_page_renders(app):
    at, _ = app
    for page in ("💸 Movimenti", "⚽ Arbitraggio", "📊 Statistiche", "⚙️ Gestione", "🏠 Dashboard"):
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception, page


def test_add_and_edit_movement_through_form(app):
    at, service = app
    at.button(key="top_new").click().run()
    widget(at.number_input, "Importo (€)").set_value(25.5)
    widget(at.text_input, "Motivo / descrizione").set_value("Spesa di prova")
    widget(at.text_input, "Provenienza / destinazione").set_value("Supermercato")
    widget(at.button, "Salva movimento").click().run()
    assert not at.exception
    assert total_balance(service.snapshot()) == -25.5
    at.sidebar.radio[0].set_value("💸 Movimenti").run()
    at.selectbox(key="selected_movement").select_index(1).run()
    widget(at.button, "Modifica movimento").click().run()
    widget(at.number_input, "Importo (€)").set_value(30)
    widget(at.button, "Salva modifiche").click().run()
    assert not at.exception
    assert total_balance(service.snapshot()) == -30
    assert len(service.snapshot().movements) == 1


def test_match_form_edit_and_delete_update_finances(app):
    at, service = app
    at.sidebar.radio[0].set_value("⚽ Arbitraggio").run()
    at.button(key="top_new").click().run()
    widget(at.text_input, "Numero pacco").set_value("0007")
    widget(at.text_input, "Squadra di casa").set_value("Casa")
    widget(at.text_input, "Squadra ospite").set_value("Ospiti")
    widget(at.selectbox, "Stato pagamento").set_value("Ricevuto").run()
    widget(at.selectbox, "Accredita sul conto").set_value("Conto personale")
    widget(at.number_input, "Compenso previsto (€)").set_value(55)
    widget(at.button, "Salva partita").click().run()
    assert not at.exception
    assert total_balance(service.snapshot()) == 55
    at.selectbox(key="selected_match").select_index(1).run()
    widget(at.button, "Modifica partita").click().run()
    widget(at.number_input, "Compenso previsto (€)").set_value(70)
    widget(at.button, "Salva modifiche").click().run()
    assert not at.exception
    assert total_balance(service.snapshot()) == 70
    assert len(service.snapshot().movements) == 1
    at.selectbox(key="selected_match").select_index(1).run()
    widget(at.button, "Elimina partita").click().run()
    widget(at.checkbox, "Confermo l'eliminazione").check().run()
    widget(at.button, "Elimina definitivamente").click().run()
    assert not at.exception
    assert service.snapshot().matches.empty
    assert total_balance(service.snapshot()) == 0


def test_invalid_form_can_be_corrected(app):
    at, service = app
    at.button(key="top_new").click().run()
    widget(at.button, "Salva movimento").click().run()
    assert not at.exception
    assert at.error and service.snapshot().movements.empty
    widget(at.number_input, "Importo (€)").set_value(10)
    widget(at.text_input, "Motivo / descrizione").set_value("Valido")
    widget(at.button, "Salva movimento").click().run()
    assert not at.exception
    assert len(service.snapshot().movements) == 1


def test_period_filters_and_search_with_no_results(app):
    at, service = app
    service.save_movement(kind="Entrata", amount=100, date=today(), description="Stipendio", category="Stipendio", source="Lavoro", account="Conto personale")
    at.sidebar.radio[0].set_value("💸 Movimenti").run()
    at.text_input(key="movement_search").set_value("inesistente").run()
    assert not at.exception
    at.text_input(key="movement_search").set_value("[regex]").run()
    assert not at.exception
    at.text_input(key="movement_search").set_value("").run()
    for mode in ("Mese", "Anno", "Periodo", "Tutto"):
        at.radio(key="movements_mode").set_value(mode).run()
        assert not at.exception
    at.sidebar.radio[0].set_value("📊 Statistiche").run()
    for mode in ("Mese", "Anno", "Periodo", "Tutto"):
        at.radio(key="statistics_mode").set_value(mode).run()
        assert not at.exception


def test_create_category_and_update_opening_balance(app):
    at, service = app
    at.sidebar.radio[0].set_value("⚙️ Gestione").run()
    widget(at.text_input, "Nome della categoria").set_value("Viaggi")
    widget(at.button, "Crea categoria").click().run()
    assert not at.exception
    assert any(row["Nome"] == "Viaggi" for row in service.snapshot().categories)
    at.selectbox(key="manage_account").select_index(1).run()
    widget(at.number_input, "Modifica saldo iniziale (€)").set_value(750)
    widget(at.button, "Salva conto").click().run()
    assert not at.exception
    assert total_balance(service.snapshot()) == 750


def test_missing_all_accounts_and_categories_render_without_errors(app):
    at, service = app
    snapshot = service.snapshot()
    for record in snapshot.categories:
        service.delete_category(record["ID"])
    for record in snapshot.accounts:
        service.delete_account(record["ID"])
    for page in ("🏠 Dashboard", "💸 Movimenti", "⚽ Arbitraggio", "📊 Statistiche", "⚙️ Gestione"):
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception


def test_search_an_empty_archive(app):
    at, _ = app
    at.sidebar.radio[0].set_value("💸 Movimenti").run()
    at.text_input(key="movement_search").set_value("prova").run()
    assert not at.exception


def test_category_rename_and_delete_through_settings(app):
    at, service = app
    service.save_movement(kind="Uscita", amount=12, date=today(), description="Spesa", category="Cibo", source="Negozio", account="Conto personale")
    category_id = next(row["ID"] for row in service.snapshot().categories if row["Nome"] == "Cibo")
    at.sidebar.radio[0].set_value("⚙️ Gestione").run()
    at.selectbox(key="manage_category").set_value(category_id).run()
    widget(at.text_input, "Rinomina categoria").set_value("Alimentari")
    widget(at.button, "Salva categoria").click().run()
    assert not at.exception
    assert service.snapshot().tables["Movimenti"][0]["Categoria"] == "Alimentari"
    at.selectbox(key="manage_category").set_value(category_id).run()
    widget(at.selectbox, "Riclassifica i movimenti").set_value("Altro")
    widget(at.checkbox, "Confermo l'eliminazione della categoria").check()
    widget(at.button, "Elimina categoria").click().run()
    assert not at.exception
    assert service.snapshot().tables["Movimenti"][0]["Categoria"] == "Altro"


def test_account_rename_and_reassignment_through_settings(app):
    at, service = app
    account_id = service.snapshot().accounts[0]["ID"]
    service.save_account(name="Conto personale", opening_balance=100, account_id=account_id)
    service.save_match(date=today(), package="17", home="A", away="B", fee=45, status="Ricevuto", received_date=today(), account="Conto personale", category="Arbitraggio")
    at.sidebar.radio[0].set_value("⚙️ Gestione").run()
    at.selectbox(key="manage_account").set_value(account_id).run()
    widget(at.text_input, "Rinomina conto").set_value("Principale")
    widget(at.button, "Salva conto").click().run()
    assert not at.exception
    assert service.snapshot().tables["Arbitraggio"][0]["Conto"] == "Principale"
    at.selectbox(key="manage_account").set_value(account_id).run()
    widget(at.checkbox, "Confermo l'eliminazione del conto").check()
    widget(at.button, "Elimina conto").click().run()
    assert not at.exception
    assert total_balance(service.snapshot()) == 145
    assert service.snapshot().tables["Arbitraggio"][0]["Conto"] == "Contanti"


def test_invalid_excel_shows_message_without_resetting_data(app):
    at, service = app
    service.store.path.write_bytes(b"Archivio non leggibile")
    at.run()
    assert not at.exception
    assert at.error
    assert service.store.path.read_bytes() == b"Archivio non leggibile"


def test_future_match_can_be_created_reloaded_and_rescheduled(app):
    at, service = app
    tomorrow = today() + timedelta(days=1)
    at.sidebar.radio[0].set_value("⚽ Arbitraggio").run()
    at.button(key="top_new").click().run()
    assert widget(at.selectbox, "Stato pagamento").value == "Da ricevere"
    assert widget(at.date_input, "Data della partita").max > tomorrow
    widget(at.date_input, "Data della partita").set_value(tomorrow)
    widget(at.text_input, "Numero pacco").set_value("0018")
    widget(at.text_input, "Squadra di casa").set_value("Casa")
    widget(at.text_input, "Squadra ospite").set_value("Ospiti")
    widget(at.number_input, "Compenso previsto (€)").set_value(50)
    widget(at.button, "Salva partita").click().run()
    assert not at.exception and not at.error
    record = service.snapshot().tables["Arbitraggio"][0]
    assert record["Data partita"] == tomorrow
    assert record["Stato"] == "Da ricevere"
    assert service.snapshot().movements.empty and total_balance(service.snapshot()) == 0
    at.run()
    assert not at.exception and not at.error
    at.selectbox(key="selected_match").set_value(record["ID"]).run()
    widget(at.button, "Modifica partita").click().run()
    assert widget(at.date_input, "Data della partita").value == tomorrow
    next_week = today() + timedelta(days=7)
    widget(at.date_input, "Data della partita").set_value(next_week)
    widget(at.button, "Salva modifiche").click().run()
    assert not at.exception and not at.error
    updated = service.snapshot().tables["Arbitraggio"][0]
    assert updated["ID"] == record["ID"] and updated["Data partita"] == next_week
    assert service.snapshot().movements.empty and total_balance(service.snapshot()) == 0


def test_transfer_form_filters_edit_and_delete_update_both_accounts(app):
    at, service = app
    source = service.snapshot().accounts[0]
    service.save_account(name=source["Nome"], opening_balance=100, account_id=source["ID"])
    at.sidebar.radio[0].set_value("💸 Movimenti").run()
    at.button(key="top_new").click().run()
    widget(at.radio, "Tipo di movimento").set_value("Giroconto").run()
    widget(at.number_input, "Importo (€)").set_value(30)
    widget(at.selectbox, "Conto di partenza").set_value("Conto personale")
    widget(at.selectbox, "Conto di arrivo").set_value("Contanti")
    widget(at.button, "Salva giroconto").click().run()
    assert not at.exception and not at.error
    assert total_balance(service.snapshot()) == 100
    record = service.snapshot().tables["Movimenti"][0]
    assert record["Tipo"] == "Giroconto" and record["Conto_destinazione"] == "Contanti"
    at.selectbox(key="movement_kind_filter").set_value("Giroconto").run()
    at.selectbox(key="movement_account_filter").set_value("Contanti").run()
    assert not at.exception and len(at.dataframe[0].value) == 1
    assert at.dataframe[0].value.iloc[0]["Conto"] == "Conto personale → Contanti"
    assert at.dataframe[0].value.iloc[0]["Importo"] == "30,00 €"
    at.selectbox(key="selected_movement").set_value(record["ID"]).run()
    widget(at.button, "Modifica movimento").click().run()
    assert widget(at.radio, "Tipo di movimento").value == "Giroconto"
    widget(at.number_input, "Importo (€)").set_value(40)
    widget(at.button, "Salva modifiche").click().run()
    assert not at.exception and not at.error
    assert len(service.snapshot().movements) == 1 and total_balance(service.snapshot()) == 100
    at.sidebar.radio[0].set_value("📊 Statistiche").run()
    at.selectbox(key="statistics_account").set_value("Contanti").run()
    assert not at.exception
    at.sidebar.radio[0].set_value("🏠 Dashboard").run()
    assert not at.exception
    assert any("Conto personale → Contanti" in element.value for element in at.markdown)
    at.sidebar.radio[0].set_value("💸 Movimenti").run()
    at.selectbox(key="selected_movement").set_value(record["ID"]).run()
    widget(at.button, "Elimina movimento").click().run()
    widget(at.checkbox, "Confermo l'eliminazione").check().run()
    widget(at.button, "Elimina definitivamente").click().run()
    assert not at.exception and service.snapshot().movements.empty
    assert total_balance(service.snapshot()) == 100


def test_account_rename_through_settings_updates_transfer_destination(app):
    at, service = app
    service.save_movement(kind="Giroconto", amount=20, date=today(), description="", category="", source="", account="Conto personale", destination_account="Contanti")
    account = service.snapshot().accounts[1]
    at.sidebar.radio[0].set_value("⚙️ Gestione").run()
    at.selectbox(key="manage_account").set_value(account["ID"]).run()
    widget(at.text_input, "Rinomina conto").set_value("Portafoglio")
    widget(at.button, "Salva conto").click().run()
    assert not at.exception and not at.error
    assert service.snapshot().tables["Movimenti"][0]["Conto_destinazione"] == "Portafoglio"
    at.sidebar.radio[0].set_value("💸 Movimenti").run()
    at.button(key="top_new").click().run()
    widget(at.radio, "Tipo di movimento").set_value("Giroconto").run()
    assert "Portafoglio" in widget(at.selectbox, "Conto di arrivo").options


def test_transfer_form_requires_a_second_account(app):
    at, service = app
    service.delete_account(service.snapshot().accounts[1]["ID"])
    at.sidebar.radio[0].set_value("💸 Movimenti").run()
    at.button(key="top_new").click().run()
    widget(at.radio, "Tipo di movimento").set_value("Giroconto").run()
    assert not at.exception
    assert any("almeno due conti" in element.value for element in at.info)
