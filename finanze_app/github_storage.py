"""Excel persistente su GitHub: nessun database esterno.

Il file remoto è autorevole. La copia locale è solo una cache ricostruibile.
Gli aggiornamenti usano lo SHA precedente per evitare sovrascritture concorrenti.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .errors import ConflictError, StorageError, ValidationError
from .storage import ExcelStore


class UncertainWriteError(StorageError):
    """La connessione è caduta: il server potrebbe aver già accettato il commit."""


class GitHubFile:
    def __init__(self, *, repository, token, branch="dati", path="finanze.xlsx"):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository or ""):
            raise ValidationError("Nei Secrets imposta repository nel formato NOMEUTENTE/NOMEREPOSITORY.")
        if not token or not isinstance(token, str):
            raise ValidationError("Manca il token GitHub nei Secrets di Streamlit.")
        if not branch or not isinstance(branch, str):
            raise ValidationError("Indica il ramo GitHub dei dati, normalmente dati.")
        parts = (path or "").split("/")
        if any(part in ("", ".", "..") for part in parts) or not path.endswith(".xlsx"):
            raise ValidationError("Il percorso dell'archivio deve essere un file .xlsx dentro il repository.")
        self.repository, self.branch, self.path = repository, branch, path
        self._token = token
        self._base = f"https://api.github.com/repos/{repository}"
        self._file_url = f"{self._base}/contents/{quote(path, safe='/')}"

    def _request(self, method, url, payload=None, *, allow_missing=False):
        request = Request(
            url, method=method,
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "Finanze-Streamlit",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code == 404 and allow_missing:
                return None
            if exc.code in (401, 403):
                raise StorageError("GitHub ha negato l'accesso. Controlla token, scadenza e permessi Contents: Read and write.") from None
            if exc.code in (409, 422) and method == "PUT":
                raise ConflictError("Il file è cambiato oppure il ramo rifiuta il salvataggio. Aggiorna i dati e controlla che il ramo dati sia scrivibile.") from None
            if exc.code == 404:
                raise StorageError("Repository o ramo GitHub non trovato. Controlla i Secrets e crea il ramo dati.") from None
            raise StorageError("GitHub non ha completato la richiesta. Riprova dopo aver aggiornato i dati.") from None
        except (URLError, TimeoutError, OSError):
            if method == "PUT":
                raise UncertainWriteError("Connessione interrotta durante il salvataggio.") from None
            raise StorageError("GitHub non è raggiungibile. Nessun dato locale verrà usato come sostituto dell'archivio remoto.") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            if method == "PUT":
                raise UncertainWriteError("Risposta al salvataggio non leggibile.") from None
            raise StorageError("La risposta di GitHub non è leggibile. Riprova.") from None

    def read(self):
        url = f"{self._file_url}?ref={quote(self.branch, safe='')}"
        result = self._request("GET", url, allow_missing=True)
        if result is None:
            # A 404 can also mean missing permission. Verify the branch before
            # treating it as an absent file and creating a new workbook.
            self._request("GET", f"{self._base}/branches/{quote(self.branch, safe='')}")
            return None
        if not isinstance(result, dict) or result.get("type") != "file" or not result.get("sha"):
            raise StorageError("Il percorso GitHub non indica un file Excel valido.")
        sha = result["sha"]
        if result.get("encoding") != "base64":
            # The Contents API omits inline data above 1 MB. A blob addressed by
            # the immutable SHA avoids mixing a newer file with the old SHA.
            result = self._request("GET", f"{self._base}/git/blobs/{quote(sha, safe='')}")
        try:
            if result.get("encoding") != "base64":
                raise ValueError
            content = base64.b64decode("".join(result["content"].split()), validate=True)
        except (KeyError, ValueError, binascii.Error, TypeError):
            raise StorageError("Il file Excel ricevuto da GitHub non è leggibile.") from None
        return content, sha

    def write(self, content, previous_sha):
        payload = {
            "message": "Aggiorna archivio finanze.xlsx",
            "branch": self.branch,
            "content": base64.b64encode(content).decode("ascii"),
        }
        if previous_sha:
            payload["sha"] = previous_sha
        try:
            result = self._request("PUT", self._file_url, payload)
        except UncertainWriteError:
            # Never retry a financial operation blindly: a timed-out commit
            # might already contain the newly generated movement IDs.
            latest = self.read()
            if latest is not None and latest[0] == content:
                return latest[1]
            raise StorageError("Salvataggio non confermato. Premi Aggiorna dati e controlla lo storico prima di reinserire il movimento.") from None
        try:
            return result["content"]["sha"]
        except (KeyError, TypeError):
            latest = self.read()
            if latest is not None and latest[0] == content:
                return latest[1]
            raise StorageError("GitHub non ha confermato il salvataggio. Aggiorna i dati prima di riprovare.") from None


class GitHubExcelStore(ExcelStore):
    is_remote = True

    def __init__(self, path, remote):
        super().__init__(path)
        self.remote = remote
        self._remote_sha = None

    def _install(self, content):
        descriptor, name = tempfile.mkstemp(prefix=".finanze-cache-", suffix=".xlsx", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def _sync(self):
        current = self.remote.read()
        if current is None:
            self._remote_sha = None
            self.path.unlink(missing_ok=True)
        else:
            content, self._remote_sha = current
            self._install(content)

    def _load(self):
        self._sync()
        return super()._load()

    def _save(self, workbook, fingerprint):
        buffer = io.BytesIO()
        workbook.save(buffer)
        content = buffer.getvalue()
        # Commit is the durable save. A local cache failure after the successful
        # commit must not invite the user to duplicate an already saved entry.
        self._remote_sha = self.remote.write(content, self._remote_sha)
        try:
            self._install(content)
        except OSError:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass

    def download(self):
        with self._locked():
            current = self.remote.read()
            if current is None:
                raise StorageError("L'archivio non è ancora presente su GitHub. Aggiorna i dati per crearlo.")
            return current[0]


def cloud_store(*, repository, token, branch="dati", path="finanze.xlsx"):
    remote = GitHubFile(repository=repository, token=token, branch=branch, path=path)
    cache_id = hashlib.sha256(f"{repository}\n{branch}\n{path}".encode()).hexdigest()[:20]
    cache_path = Path(tempfile.gettempdir()) / "finanze-streamlit" / cache_id / "finanze.xlsx"
    return GitHubExcelStore(cache_path, remote)
