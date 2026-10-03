"""Regole dei movimenti, delle partite, delle categorie e dei conti."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from .errors import ConflictError, ValidationError
from .storage import SCHEMA, ExcelStore
from .utils import as_date, cents, money, new_id, text, timestamp


KINDS = ("Entrata", "Uscita")
CATEGORY_KINDS = ("Entrata", "Uscita", "Entrambe")


@dataclass
class Snapshot:
    tables: dict

    @property
    def movements(self) -> pd.DataFrame:
        frame = pd.DataFrame(self.tables["Movimenti"], columns=SCHEMA["Movimenti"])
        frame["Data"] = pd.to_datetime(frame["Data"])
        frame["Data_creazione"] = pd.to_datetime(frame["Data_creazione"])
        return frame

    @property
    def matches(self) -> pd.DataFrame:
        frame = pd.DataFrame(self.tables["Arbitraggio"], columns=SCHEMA["Arbitraggio"])
        frame["Data partita"] = pd.to_datetime(frame["Data partita"])
        frame["Data incasso"] = pd.to_datetime(frame["Data incasso"])
        return frame

    @property
    def accounts(self) -> list[dict]:
        return self.tables["Conti"]

    @property
    def categories(self) -> list[dict]:
        return self.tables["Categorie"]

    def category_names(self, kind: str) -> list[str]:
        return sorted(
            [row["Nome"] for row in self.categories if row["Tipo"] in (kind, "Entrambe")],
            key=str.casefold,
        )

    def account_names(self) -> list[str]:
        return [row["Nome"] for row in self.accounts]


class FinanceService:
    def __init__(self, path, *, store=None):
        self.store = store if store is not None else ExcelStore(path)

    @staticmethod
    def _get(tables, sheet, record_id):
        for row in tables[sheet]:
            if row["ID"] == record_id:
                return row
        raise ConflictError("Questo elemento non esiste più. Aggiorna i dati.")

    @staticmethod
    def _expected(row, expected):
        if expected is not None and any(row.get(key) != value for key, value in expected.items()):
            raise ConflictError("Questo elemento è stato modificato. Chiudi il modulo, aggiorna i dati e riprova.")

    @staticmethod
    def _unique(tables, sheet, name, exclude_id=None):
        if any(row["Nome"].casefold() == name.casefold() and row["ID"] != exclude_id for row in tables[sheet]):
            raise ValidationError("Questo nome esiste già. Scegli un nome diverso.")

    @staticmethod
    def _validate_account(tables, name):
        if name not in [row["Nome"] for row in tables["Conti"]]:
            raise ValidationError("Seleziona un conto esistente. Puoi crearlo in Gestione.")

    @staticmethod
    def _validate_category(tables, name, kind):
        if not name:
            return
        category = next((row for row in tables["Categorie"] if row["Nome"] == name), None)
        if category is None or category["Tipo"] not in (kind, "Entrambe"):
            raise ValidationError("La categoria non è disponibile per questo tipo di movimento.")

    def _normalize(self, tables):
        for sheet in SCHEMA:
            seen = set()
            for number, row in enumerate(tables[sheet], 2):
                try:
                    row["ID"] = text(row.get("ID"), label="ID", required=True, limit=80)
                    if row["ID"] in seen:
                        raise ValidationError("ID duplicato.")
                    seen.add(row["ID"])
                    if sheet == "Conti":
                        row["Nome"] = text(row.get("Nome"), label="Nome", required=True, limit=80)
                        row["Saldo_iniziale"] = money(row.get("Saldo_iniziale", 0))
                    elif sheet == "Categorie":
                        row["Nome"] = text(row.get("Nome"), label="Nome", required=True, limit=80)
                        row["Tipo"] = text(row.get("Tipo"))
                        if row["Tipo"] not in CATEGORY_KINDS:
                            raise ValidationError("Il tipo deve essere Entrata, Uscita o Entrambe.")
                    elif sheet == "Movimenti":
                        row["Data"] = as_date(row.get("Data"), past_only=True)
                        row["Tipo"] = text(row.get("Tipo"))
                        if row["Tipo"] not in KINDS:
                            raise ValidationError("Il tipo deve essere Entrata o Uscita.")
                        row["Arbitraggio_ID"] = text(row.get("Arbitraggio_ID"))
                        row["Importo"] = money(row.get("Importo"), positive=not bool(row["Arbitraggio_ID"]), nonnegative=True)
                        for field in ("Categoria", "Fonte", "Note", "Conto", "Descrizione"):
                            row[field] = text(row.get(field), label=field, limit=5000 if field == "Note" else 2000)
                        if not row["Descrizione"]:
                            raise ValidationError("La descrizione è obbligatoria.")
                        created = row.get("Data_creazione")
                        if isinstance(created, str):
                            try:
                                created = datetime.fromisoformat(created)
                            except ValueError as exc:
                                raise ValidationError("Data_creazione non valida.") from exc
                        if not isinstance(created, datetime) or created.tzinfo is not None:
                            raise ValidationError("Data_creazione deve essere una data e ora Excel.")
                        row["Data_creazione"] = created
                    elif sheet == "Arbitraggio":
                        row["Data partita"] = as_date(row.get("Data partita"))
                        row["Compenso"] = money(row.get("Compenso"), nonnegative=True)
                        row["Km"] = money(row.get("Km") or 0, nonnegative=True)
                        row["Categoria partita"] = text(row.get("Categoria partita"), label="Categoria partita", limit=120)
                        for field in ("Numero pacco", "Squadra casa", "Squadra ospite", "Note", "Conto", "Movimento_ID", "Categoria"):
                            row[field] = text(row.get(field), label=field, limit=5000 if field == "Note" else 2000)
                        for field in ("Numero pacco", "Squadra casa", "Squadra ospite"):
                            if not row[field]:
                                raise ValidationError(f"{field} è obbligatorio.")
                        # Old records were already credited: preserve their movement and date.
                        state = text(row.get("Stato"))
                        if not state:
                            state = "Ricevuto" if row["Movimento_ID"] else "Da ricevere"
                            if state == "Ricevuto" and not row.get("Data incasso"):
                                linked = next((m for m in tables["Movimenti"] if m["ID"] == row["Movimento_ID"]), None)
                                row["Data incasso"] = linked["Data"] if linked else row["Data partita"]
                        if state not in ("Da ricevere", "Ricevuto"):
                            raise ValidationError("Stato pagamento non valido.")
                        row["Stato"] = state
                        if state == "Ricevuto":
                            row["Data incasso"] = as_date(row.get("Data incasso"), past_only=True)
                            if row["Data incasso"] < row["Data partita"]:
                                raise ValidationError("L'incasso non può precedere la partita.")
                        else:
                            row["Data incasso"] = None
                except ValidationError as exc:
                    raise ValidationError(f"{sheet}, riga {number}: {exc}") from exc
        for sheet in ("Conti", "Categorie"):
            names = [row["Nome"].casefold() for row in tables[sheet]]
            if len(names) != len(set(names)):
                raise ValidationError(f"Nel foglio {sheet} ci sono nomi duplicati.")

    def _validate_relations(self, tables):
        movements = {row["ID"]: row for row in tables["Movimenti"]}
        matches = {row["ID"]: row for row in tables["Arbitraggio"]}
        linked_ids = set()
        for movement in movements.values():
            self._validate_account(tables, movement["Conto"])
            self._validate_category(tables, movement["Categoria"], movement["Tipo"])
            match_id = movement["Arbitraggio_ID"]
            if match_id and (match_id not in matches or matches[match_id]["Movimento_ID"] != movement["ID"]):
                raise ValidationError("Un movimento di arbitraggio non ha la partita collegata. Controlla gli ID nell'Excel.")
        for match in matches.values():
            if match["Conto"]:
                self._validate_account(tables, match["Conto"])
            self._validate_category(tables, match["Categoria"], "Entrata")
            movement_id = match["Movimento_ID"]
            if match["Stato"] == "Da ricevere":
                if movement_id:
                    raise ValidationError("Una partita da ricevere non deve avere un'entrata collegata.")
                continue
            self._validate_account(tables, match["Conto"])
            if movement_id in linked_ids or movement_id not in movements:
                raise ValidationError("Una partita ha un movimento mancante o duplicato. Controlla gli ID nell'Excel.")
            linked_ids.add(movement_id)
            movement = movements[movement_id]
            if (
                movement["Arbitraggio_ID"] != match["ID"]
                or movement["Tipo"] != "Entrata"
                or movement["Fonte"] != "Arbitraggio"
                or cents(movement["Importo"]) != cents(match["Compenso"])
                or movement["Data"] != match["Data incasso"]
                or movement["Conto"] != match["Conto"]
                or movement["Categoria"] != match["Categoria"]
            ):
                raise ValidationError("Una partita e la sua entrata non coincidono. Modifica le partite dalla pagina Arbitraggio.")

    def snapshot(self) -> Snapshot:
        tables = self.store.read()
        self._normalize(tables)
        self._validate_relations(tables)
        return Snapshot(tables)

    def _mutate(self, operation):
        def transaction(tables):
            self._normalize(tables)
            self._validate_relations(tables)
            result = operation(tables)
            self._normalize(tables)
            self._validate_relations(tables)
            return result
        return self.store.transaction(transaction)

    def save_movement(self, *, kind, amount, date, description, category, source, account, notes="", movement_id=None, expected=None):
        def operation(tables):
            if kind not in KINDS:
                raise ValidationError("Seleziona Entrata o Uscita.")
            self._validate_account(tables, account)
            category_name = text(category)
            self._validate_category(tables, category_name, kind)
            row = None
            if movement_id:
                row = self._get(tables, "Movimenti", movement_id)
                self._expected(row, expected)
                if row["Arbitraggio_ID"]:
                    raise ValidationError("Modifica questa entrata dalla pagina Arbitraggio: è collegata a una partita.")
            values = {
                "Data": as_date(date, past_only=True), "Tipo": kind,
                "Importo": money(amount, positive=True), "Categoria": category_name,
                "Descrizione": text(description, label="La descrizione", required=True),
                "Fonte": text(source), "Conto": account, "Note": text(notes, limit=5000),
            }
            if row is None:
                row = {"ID": new_id("M"), "Data_creazione": timestamp(), "Arbitraggio_ID": "", **values}
                tables["Movimenti"].append(row)
            else:
                row.update(values)
            return row["ID"]
        return self._mutate(operation)

    def delete_movement(self, movement_id, *, expected=None):
        def operation(tables):
            row = self._get(tables, "Movimenti", movement_id)
            self._expected(row, expected)
            if row["Arbitraggio_ID"]:
                tables["Arbitraggio"] = [match for match in tables["Arbitraggio"] if match["ID"] != row["Arbitraggio_ID"]]
            tables["Movimenti"] = [movement for movement in tables["Movimenti"] if movement["ID"] != movement_id]
        self._mutate(operation)

    def _set_payment(self, tables, row, *, status, received_date, account):
        if status not in ("Da ricevere", "Ricevuto"):
            raise ValidationError("Seleziona Da ricevere o Ricevuto.")
        if status == "Da ricevere":
            tables["Movimenti"] = [m for m in tables["Movimenti"] if m["ID"] != row["Movimento_ID"]]
            row.update({"Stato": status, "Data incasso": None, "Movimento_ID": "", "Conto": ""})
            return
        self._validate_account(tables, account)
        payment_date = as_date(received_date, past_only=True)
        if payment_date < row["Data partita"]:
            raise ValidationError("La data d'incasso non può precedere la partita.")
        row.update({"Stato": status, "Data incasso": payment_date, "Conto": account})
        if row["Movimento_ID"]:
            movement = self._get(tables, "Movimenti", row["Movimento_ID"])
        else:
            row["Movimento_ID"] = new_id("M")
            movement = {"ID": row["Movimento_ID"], "Data_creazione": timestamp(), "Arbitraggio_ID": row["ID"]}
            tables["Movimenti"].append(movement)
        movement.update({
            "Data": payment_date, "Tipo": "Entrata", "Importo": row["Compenso"],
            "Categoria": row["Categoria"], "Descrizione": f"{row['Squadra casa']} – {row['Squadra ospite']} · Pacco {row['Numero pacco']}",
            "Fonte": "Arbitraggio", "Note": row["Note"], "Conto": account,
        })

    def save_match(self, *, date, package, home, away, fee, account="", category="", notes="", match_id=None, expected=None, status="Da ricevere", received_date=None, km=None, match_category=None):
        def operation(tables):
            category_name = text(category)
            self._validate_category(tables, category_name, "Entrata")
            row = None
            if match_id:
                row = self._get(tables, "Arbitraggio", match_id)
                self._expected(row, expected)
            values = {
                "Data partita": as_date(date),
                "Numero pacco": text(package, label="Il numero pacco", required=True, limit=80),
                "Squadra casa": text(home, label="La squadra di casa", required=True, limit=120),
                "Squadra ospite": text(away, label="La squadra ospite", required=True, limit=120),
                "Compenso": money(fee, nonnegative=True), "Note": text(notes, limit=5000),
                "Categoria": category_name,
                "Km": money(km if km is not None else (row or {}).get("Km", 0), nonnegative=True),
                "Categoria partita": text(match_category if match_category is not None else (row or {}).get("Categoria partita", ""), label="Categoria partita", limit=120),
            }
            if row is None:
                row = {"ID": new_id("P"), "Movimento_ID": "", **values}
                tables["Arbitraggio"].append(row)
            else:
                row.update(values)
            self._set_payment(tables, row, status=status, received_date=received_date, account=account)
            return row["ID"]
        return self._mutate(operation)

    def update_match_payments(self, updates):
        """Save all edited payments atomically, with stale-record checks."""
        def operation(tables):
            seen = set()
            for update in updates:
                if update["ID"] in seen:
                    raise ValidationError("Partita duplicata nell'aggiornamento.")
                seen.add(update["ID"])
                row = self._get(tables, "Arbitraggio", update["ID"])
                self._expected(row, update["expected"])
                self._set_payment(tables, row, status=update["Stato"], received_date=update["Data incasso"], account=update["Conto"])
        self._mutate(operation)

    def delete_match(self, match_id, *, expected=None):
        def operation(tables):
            row = self._get(tables, "Arbitraggio", match_id)
            self._expected(row, expected)
            tables["Movimenti"] = [movement for movement in tables["Movimenti"] if movement["ID"] != row["Movimento_ID"]]
            tables["Arbitraggio"] = [match for match in tables["Arbitraggio"] if match["ID"] != match_id]
        self._mutate(operation)

    def save_category(self, *, name, kind, category_id=None, expected=None):
        def operation(tables):
            label = text(name, label="Il nome", required=True, limit=80)
            if kind not in CATEGORY_KINDS:
                raise ValidationError("Seleziona il tipo della categoria.")
            self._unique(tables, "Categorie", label, category_id)
            if category_id:
                row = self._get(tables, "Categorie", category_id)
                self._expected(row, expected)
                old_name = row["Nome"]
                if (any(m["Categoria"] == old_name and kind not in (m["Tipo"], "Entrambe") for m in tables["Movimenti"])
                        or any(m["Categoria"] == old_name and kind not in ("Entrata", "Entrambe") for m in tables["Arbitraggio"])):
                    raise ValidationError("Questa categoria è già usata per un altro tipo di movimento. Scegli Entrambe o riclassifica i movimenti.")
                row.update({"Nome": label, "Tipo": kind})
                for sheet in ("Movimenti", "Arbitraggio"):
                    for record in tables[sheet]:
                        if record["Categoria"] == old_name:
                            record["Categoria"] = label
            else:
                row = {"ID": new_id("C"), "Nome": label, "Tipo": kind}
                tables["Categorie"].append(row)
            return row["ID"]
        return self._mutate(operation)

    def delete_category(self, category_id, *, replacement="", expected=None):
        def operation(tables):
            row = self._get(tables, "Categorie", category_id)
            self._expected(row, expected)
            target = text(replacement)
            if target == row["Nome"]:
                raise ValidationError("Seleziona un'altra categoria.")
            if target and target not in [category["Nome"] for category in tables["Categorie"]]:
                raise ValidationError("Seleziona una categoria esistente.")
            for record in tables["Movimenti"]:
                if record["Categoria"] == row["Nome"]:
                    self._validate_category(tables, target, record["Tipo"])
                    record["Categoria"] = target
            for record in tables["Arbitraggio"]:
                if record["Categoria"] == row["Nome"]:
                    self._validate_category(tables, target, "Entrata")
                    record["Categoria"] = target
            tables["Categorie"] = [category for category in tables["Categorie"] if category["ID"] != category_id]
        self._mutate(operation)

    def save_account(self, *, name, opening_balance=0, account_id=None, expected=None):
        def operation(tables):
            label = text(name, label="Il nome", required=True, limit=80)
            initial = money(opening_balance)
            self._unique(tables, "Conti", label, account_id)
            if account_id:
                row = self._get(tables, "Conti", account_id)
                self._expected(row, expected)
                old_name = row["Nome"]
                row.update({"Nome": label, "Saldo_iniziale": initial})
                for sheet in ("Movimenti", "Arbitraggio"):
                    for record in tables[sheet]:
                        if record["Conto"] == old_name:
                            record["Conto"] = label
            else:
                row = {"ID": new_id("A"), "Nome": label, "Saldo_iniziale": initial}
                tables["Conti"].append(row)
            return row["ID"]
        return self._mutate(operation)

    def delete_account(self, account_id, *, replacement=None, expected=None):
        def operation(tables):
            row = self._get(tables, "Conti", account_id)
            self._expected(row, expected)
            used = any(m["Conto"] == row["Nome"] for m in tables["Movimenti"])
            if replacement:
                if replacement == row["Nome"]:
                    raise ValidationError("Seleziona un altro conto.")
                self._validate_account(tables, replacement)
                target = next(account for account in tables["Conti"] if account["Nome"] == replacement)
                target["Saldo_iniziale"] = (cents(target["Saldo_iniziale"]) + cents(row["Saldo_iniziale"])) / 100
                for sheet in ("Movimenti", "Arbitraggio"):
                    for record in tables[sheet]:
                        if record["Conto"] == row["Nome"]:
                            record["Conto"] = replacement
            elif used or cents(row["Saldo_iniziale"]) != 0:
                raise ValidationError("Questo conto contiene soldi o movimenti. Seleziona il conto a cui riassegnarli.")
            tables["Conti"] = [account for account in tables["Conti"] if account["ID"] != account_id]
        self._mutate(operation)
