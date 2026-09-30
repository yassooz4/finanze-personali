"""Google Sheets is the only production archive. No local financial cache."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
import re
import threading

import gspread
from google.oauth2.service_account import Credentials
from google.auth.exceptions import GoogleAuthError
from requests.exceptions import RequestException
import streamlit as st

from .errors import ConflictError, StorageError
from .storage import SCHEMA, DEFAULT_CATEGORIES
from .utils import new_id

DATE_COLUMNS = {"Data", "Data partita", "Data incasso"}
EPOCH = datetime(1899, 12, 30)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(spreadsheet_id):
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(spreadsheet_id, threading.RLock())


def _error(exc):
    # Never display raw HTTP responses or credentials in the app.
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (401, 403) or isinstance(exc, PermissionError):
        return StorageError("Google Sheets ha negato l'accesso. Abilita Google Sheets API e condividi il foglio con il client_email del Service Account come Editor.")
    if status == 429:
        return StorageError("Google Sheets ha temporaneamente limitato le richieste. Attendi un minuto e premi Aggiorna dati.")
    return StorageError("Non riesco a leggere o aggiornare Google Sheets. Controlla connessione, ID del foglio e autorizzazioni. Nessun archivio locale verrà usato al suo posto.")


def _decode(header, value):
    if value == "" or value is None:
        return None
    if header in DATE_COLUMNS or header == "Data_creazione":
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            try:
                parsed = EPOCH + timedelta(days=value)
                # Float serials can carry rounding error at the microsecond level.
                parsed = (parsed + timedelta(microseconds=500000)).replace(microsecond=0)
                return parsed if header == "Data_creazione" else parsed.date()
            except (OverflowError, ValueError):
                raise StorageError(f"Data non valida nella colonna {header} di Google Sheets.") from None
        if header == "Data_creazione" and isinstance(value, str):
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
    return value


def _equivalent(left, right):
    def canonical(value):
        if isinstance(value, dict):
            return {k: canonical(v) for k, v in value.items() if v is not None and v != ""}
        if isinstance(value, list):
            return [canonical(v) for v in value]
        return None if value == "" else value
    return canonical(left) == canonical(right)


def _cell(header, value, *, known=True):
    if value is None or value == "":
        return {}
    if isinstance(value, datetime):
        return {"userEnteredValue": {"numberValue": (value - EPOCH).total_seconds() / 86400}}
    if isinstance(value, date):
        return {"userEnteredValue": {"numberValue": (value - EPOCH.date()).days}}
    if isinstance(value, bool):
        return {"userEnteredValue": {"boolValue": value}}
    if isinstance(value, (int, float)):
        return {"userEnteredValue": {"numberValue": value}}
    # Financial descriptions are always literal, even if they start with '='.
    key = "formulaValue" if not known and str(value).startswith("=") else "stringValue"
    return {"userEnteredValue": {key: str(value)}}


def _seed(name):
    if name == "Conti":
        return [{"ID": new_id("A"), "Nome": label, "Saldo_iniziale": 0.0} for label in ("Conto personale", "Contanti")]
    if name == "Categorie":
        return [{"ID": new_id("C"), "Nome": label, "Tipo": kind} for label, kind in DEFAULT_CATEGORIES]
    return []


class GoogleSheetsStore:
    is_remote = True
    backend = "google_sheets"
    path = None

    def __init__(self, spreadsheet):
        self.spreadsheet = spreadsheet
        self.spreadsheet_id = spreadsheet.id
        self.url = f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}/edit"
        self.lock = _lock_for(spreadsheet.id)
        self._meta = None

    def _metadata(self):
        result = self.spreadsheet.fetch_sheet_metadata(params={"fields": "sheets(properties)"})
        return {item["properties"]["title"]: item["properties"] for item in result.get("sheets", [])}

    def _values(self, names):
        result = self.spreadsheet.values_batch_get([f"'{name}'" for name in names], params={"valueRenderOption": "FORMULA", "dateTimeRenderOption": "SERIAL_NUMBER"})
        ranges = result.get("valueRanges", [])
        if len(ranges) != len(names):
            raise StorageError("Google Sheets ha restituito un archivio incompleto. Nessun dato viene azzerato.")
        return {name: item.get("values", []) for name, item in zip(names, ranges)}

    def _format_requests(self, name, meta, headers):
        sid = meta["sheetId"]
        requests = [{"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1}}, "fields": "gridProperties.frozenRowCount"}},
                    {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1}, "cell": {"userEnteredFormat": {"backgroundColor": {"red": .08, "green": .14, "blue": .23}, "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}}}, "fields": "userEnteredFormat"}}]
        for i, header in enumerate(headers):
            if header in DATE_COLUMNS:
                number_format = {"type": "DATE", "pattern": "dd/mm/yyyy"}
            elif header == "Data_creazione":
                number_format = {"type": "DATE_TIME", "pattern": "dd/mm/yyyy hh:mm:ss"}
            elif header in ("Compenso", "Importo", "Saldo_iniziale"):
                number_format = {"type": "NUMBER", "pattern": '#,##0.00" €"'}
            elif header == "Km":
                number_format = {"type": "NUMBER", "pattern": "0.0"}
            elif header == "Numero pacco":
                number_format = {"type": "TEXT", "pattern": "@"}
            else:
                continue
            requests.append({"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 1, "startColumnIndex": i, "endColumnIndex": i+1}, "cell": {"userEnteredFormat": {"numberFormat": number_format}}, "fields": "userEnteredFormat.numberFormat"}})
        return requests

    def _ensure(self):
        if self._meta is not None:
            return
        metadata = self._metadata()
        existing = [name for name in SCHEMA if name in metadata]
        grids = self._values(existing) if existing else {}
        requests = []
        next_id = max([m["sheetId"] for m in metadata.values()] + [0]) + 1
        for name, schema in SCHEMA.items():
            if name not in metadata:
                meta = {"title": name, "sheetId": next_id, "gridProperties": {"rowCount": 1000, "columnCount": max(26, len(schema))}}
                next_id += 1
                requests.append({"addSheet": {"properties": meta}})
                metadata[name] = meta
                grids[name] = []
            grid = grids[name]
            if not grid or not any(grid[0]):
                if any(any(v not in (None, "") for v in row) for row in grid[1:]):
                    raise StorageError(f"La scheda {name} contiene dati senza intestazioni. Non è stata sovrascritta.")
                headers = list(schema)
                rows = [{"values": [_cell(h, h) for h in headers]}]
                rows.extend({"values": [_cell(h, r.get(h)) for h in headers]} for r in _seed(name))
                requests.append({"updateCells": {"start": {"sheetId": metadata[name]["sheetId"], "rowIndex": 0, "columnIndex": 0}, "rows": rows, "fields": "userEnteredValue"}})
                requests.extend(self._format_requests(name, metadata[name], headers))
            else:
                headers = self._headers(name, grid[0], grid[1:])
                missing = [h for h in schema if h not in headers]
                if missing:
                    old_len = len(headers)
                    headers += missing
                    needed = len(headers)
                    if needed > metadata[name]["gridProperties"]["columnCount"]:
                        requests.append({"appendDimension": {"sheetId": metadata[name]["sheetId"], "dimension": "COLUMNS", "length": needed-metadata[name]["gridProperties"]["columnCount"]}})
                        metadata[name]["gridProperties"]["columnCount"] = needed
                    requests.append({"updateCells": {"start": {"sheetId": metadata[name]["sheetId"], "rowIndex": 0, "columnIndex": old_len}, "rows": [{"values": [_cell(h,h) for h in missing]}], "fields": "userEnteredValue"}})
                    requests.extend(self._format_requests(name, metadata[name], headers))
        if requests:
            self.spreadsheet.batch_update({"requests": requests})
        self._meta = metadata

    @staticmethod
    def _headers(name, raw, rows):
        headers = list(raw)
        if any(not isinstance(h, str) or not h.strip() for h in headers) or len(headers) != len(set(headers)):
            raise StorageError(f"Intestazioni vuote o duplicate nella scheda {name}. Correggile prima di salvare.")
        if any(any(v not in (None, "") for v in row[len(headers):]) for row in rows):
            raise StorageError(f"Nella scheda {name} ci sono valori in colonne senza intestazione.")
        if "ID" not in headers:
            raise StorageError(f"Nella scheda {name} manca la colonna ID. Non modificare gli identificativi delle righe.")
        return headers

    def _load(self):
        self._ensure()
        grids = self._values(list(SCHEMA))
        tables, headers = {}, {}
        for name in SCHEMA:
            grid = grids[name]
            if not grid:
                raise StorageError(f"La scheda {name} è stata svuotata. Ripristina le intestazioni dal foglio Google.")
            hs = self._headers(name, grid[0], grid[1:])
            if any(h not in hs for h in SCHEMA[name]):
                raise StorageError(f"Nella scheda {name} mancano colonne necessarie. Aggiorna l'app dopo aver ripristinato le intestazioni.")
            headers[name] = hs
            tables[name] = [{h: _decode(h, row[i] if i < len(row) else None) for i,h in enumerate(hs)} for row in grid[1:] if any(v not in (None, "") for v in row)]
        return tables, headers, grids

    def read(self):
        with self.lock:
            try:
                return self._load()[0]
            except (gspread.exceptions.GSpreadException, RequestException, GoogleAuthError, PermissionError) as exc:
                raise _error(exc) from None

    def _write_requests(self, tables, headers, grids, changed):
        requests = []
        for name in changed:
            meta = self._meta[name]
            hs = headers[name]
            rows = [{"values": [_cell(h, r.get(h), known=h in SCHEMA[name]) for h in hs]} for r in tables[name]]
            old_len = max(0, len(grids[name])-1)
            end_row = 1 + max(len(rows), old_len)
            # Never shrink the grid; expansion and row changes use one batch.
            if end_row > meta["gridProperties"]["rowCount"]:
                requests.append({"appendDimension": {"sheetId": meta["sheetId"], "dimension": "ROWS", "length": end_row-meta["gridProperties"]["rowCount"]}})
            if end_row > 1:
                requests.append({"updateCells": {"range": {"sheetId": meta["sheetId"], "startRowIndex": 1, "endRowIndex": end_row, "startColumnIndex": 0, "endColumnIndex": len(hs)}, "rows": rows, "fields": "userEnteredValue"}})
            requests.extend(self._format_requests(name, meta, hs))
        return requests

    def transaction(self, operation):
        with self.lock:
            try:
                tables, headers, grids = self._load()
                before = deepcopy(tables)
                result = operation(tables)
                changed = [name for name in SCHEMA if tables[name] != before[name]]
                if not changed:
                    return result
                # Catch external edits made while the form operation was prepared.
                latest = self._values(list(SCHEMA))
                if latest != grids:
                    raise ConflictError("Il foglio Google è cambiato durante il salvataggio. Aggiorna i dati e riprova.")
                requests = self._write_requests(tables, headers, grids, changed)
                try:
                    self.spreadsheet.batch_update({"requests": requests})
                except (gspread.exceptions.APIError, RequestException, GoogleAuthError) as exc:
                    # A timeout can happen after Google accepted the entire batch.
                    # Read back before reporting failure; never repeat the write blindly.
                    try:
                        confirmed = self._load()[0]
                    except Exception:
                        raise StorageError("Salvataggio non confermato. Premi Aggiorna dati e controlla lo storico prima di reinserire i dati.") from None
                    if not _equivalent(confirmed, tables):
                        raise StorageError("Salvataggio non confermato. Aggiorna i dati e verifica lo storico prima di riprovare.") from None
                # Confirm durable data, not a local cache.
                persisted = self._load()[0]
                if not _equivalent(persisted, tables):
                    raise ConflictError("Il foglio è stato modificato durante il salvataggio. Aggiorna e controlla lo storico prima di riprovare.")
                for name in changed:
                    self._meta[name]["gridProperties"]["rowCount"] = max(self._meta[name]["gridProperties"]["rowCount"], len(tables[name])+1)
                return result
            except (gspread.exceptions.GSpreadException, RequestException, GoogleAuthError, PermissionError) as exc:
                raise _error(exc) from None


@st.cache_resource(show_spinner=False)
def google_store(spreadsheet_id, service_account_json):
    """Cache only connection/lock, never balances, movements or sheet values."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,}", spreadsheet_id or ""):
        raise StorageError("Nei Secrets [sheets], spreadsheet_id deve contenere l'ID del foglio Google, non il link completo.")
    import json
    try:
        credentials = Credentials.from_service_account_info(json.loads(service_account_json), scopes=SCOPES)
        client = gspread.authorize(credentials)
        client.set_timeout(20)
        spreadsheet = client.open_by_key(spreadsheet_id)
    except (ValueError, TypeError, KeyError):
        raise StorageError("Credenziali Service Account non valide. Controlla la sezione [gcp_service_account] nei Secrets.") from None
    except gspread.exceptions.SpreadsheetNotFound:
        raise StorageError("Foglio Google non trovato. Controlla l'ID e condividilo con il client_email del Service Account come Editor.") from None
    except (gspread.exceptions.GSpreadException, RequestException, GoogleAuthError, PermissionError) as exc:
        raise _error(exc) from None
    return GoogleSheetsStore(spreadsheet)
