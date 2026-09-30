import base64
import hashlib

import pytest

from finanze_app.analytics import total_balance
from finanze_app.errors import ConflictError, StorageError
from finanze_app.github_storage import GitHubExcelStore, GitHubFile, UncertainWriteError
from finanze_app.service import FinanceService
from finanze_app.utils import today


class FakeRemote:
    def __init__(self, content=None):
        self.content = content
        self.sha = hashlib.sha1(content).hexdigest() if content is not None else None
        self.before_write = None
        self.commits = 0
        self.offline = False

    def read(self):
        if self.offline:
            raise StorageError("GitHub non raggiungibile")
        return (self.content, self.sha) if self.content is not None else None

    def write(self, content, previous_sha):
        if self.before_write:
            operation, self.before_write = self.before_write, None
            operation()
        if previous_sha != self.sha:
            raise ConflictError("SHA diverso")
        self.content, self.sha = content, hashlib.sha1(content).hexdigest()
        self.commits += 1
        return self.sha


def remote_service(path, remote):
    return FinanceService(path, store=GitHubExcelStore(path, remote))


def add_movement(service, description="Spesa cloud"):
    return service.save_movement(kind="Uscita", amount=20, date=today(), description=description, category="Cibo", source="Negozio", account="Conto personale")


def test_remote_excel_survives_new_machine(tmp_path):
    remote = FakeRemote()
    first = remote_service(tmp_path / "machine_a.xlsx", remote)
    assert first.snapshot().movements.empty
    add_movement(first)
    first.store.path.unlink()
    second = remote_service(tmp_path / "machine_b.xlsx", remote)
    assert len(second.snapshot().movements) == 1
    assert total_balance(second.snapshot()) == -20
    assert remote.commits == 2


def test_remote_referee_stays_synchronized_after_restart(tmp_path):
    remote = FakeRemote()
    service = remote_service(tmp_path / "a.xlsx", remote)
    service.snapshot()
    match_id = service.save_match(date=today(), package="0007", home="Casa", away="Ospiti", fee=50, account="Conto personale", category="Arbitraggio")
    recreated = remote_service(tmp_path / "new-server.xlsx", remote)
    snapshot = recreated.snapshot()
    assert total_balance(snapshot) == 50
    assert len(snapshot.matches) == len(snapshot.movements) == 1
    assert snapshot.tables["Arbitraggio"][0]["Numero pacco"] == "0007"
    recreated.delete_match(match_id)
    assert service.snapshot().movements.empty


def test_concurrent_updates_do_not_overwrite_remote(tmp_path):
    remote = FakeRemote()
    first = remote_service(tmp_path / "a.xlsx", remote)
    second = remote_service(tmp_path / "b.xlsx", remote)
    first.snapshot()
    remote.before_write = lambda: add_movement(second, "Altra sessione")
    with pytest.raises(ConflictError):
        add_movement(first, "Non deve sovrascrivere")
    assert first.snapshot().movements["Descrizione"].tolist() == ["Altra sessione"]


def test_outage_never_uses_stale_local_excel(tmp_path):
    remote = FakeRemote()
    service = remote_service(tmp_path / "a.xlsx", remote)
    service.snapshot()
    remote.offline = True
    with pytest.raises(StorageError):
        service.snapshot()
    with pytest.raises(StorageError):
        add_movement(service)
    assert remote.commits == 1


def test_remote_success_is_not_failed_if_cache_breaks(tmp_path, monkeypatch):
    remote = FakeRemote()
    service = remote_service(tmp_path / "a.xlsx", remote)
    service.snapshot()
    original = service.store._install
    calls = 0
    def install(content):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Disco temporaneo")
        return original(content)
    monkeypatch.setattr(service.store, "_install", install)
    add_movement(service)
    recreated = remote_service(tmp_path / "other.xlsx", remote)
    assert len(recreated.snapshot().movements) == 1


def test_timeout_is_verified_without_retrying_put(monkeypatch):
    client = GitHubFile(repository="utente/finanze", token="test-token")
    puts = []
    content = b"workbook bytes"
    def request(method, url, payload=None, **kwargs):
        if method == "PUT":
            puts.append(payload)
            raise UncertainWriteError("Timeout dopo commit")
        return {"type":"file", "sha":"new-sha", "encoding":"base64", "content":base64.b64encode(content).decode()}
    monkeypatch.setattr(client, "_request", request)
    assert client.write(content, "old-sha") == "new-sha"
    assert len(puts) == 1
    assert puts[0]["sha"] == "old-sha" and puts[0]["branch"] == "dati"


def test_unconfirmed_timeout_requires_refresh(monkeypatch):
    client = GitHubFile(repository="utente/finanze", token="test-token")
    def request(method, url, payload=None, **kwargs):
        if method == "PUT":
            raise UncertainWriteError("Timeout")
        return {"type":"file", "sha":"old-sha", "encoding":"base64", "content":base64.b64encode(b"old content").decode()}
    monkeypatch.setattr(client, "_request", request)
    with pytest.raises(StorageError, match="Salvataggio non confermato"):
        client.write(b"new content", "old-sha")


def test_missing_file_checks_branch_access(monkeypatch):
    client = GitHubFile(repository="utente/finanze", token="test-token")
    calls = []
    def request(method, url, payload=None, **kwargs):
        calls.append(url)
        if "/contents/" in url:
            return None
        raise StorageError("Branch non accessibile")
    monkeypatch.setattr(client, "_request", request)
    with pytest.raises(StorageError):
        client.read()
    assert "/branches/dati" in calls[-1]


def test_large_excel_uses_immutable_blob_sha(monkeypatch):
    client = GitHubFile(repository="utente/finanze", token="test-token")
    calls = []
    def request(method, url, payload=None, **kwargs):
        calls.append(url)
        if "/contents/" in url:
            return {"type":"file", "sha":"stable-sha", "encoding":"none", "content":""}
        return {"encoding":"base64", "content":base64.b64encode(b"large workbook").decode()}
    monkeypatch.setattr(client, "_request", request)
    assert client.read() == (b"large workbook", "stable-sha")
    assert calls[-1].endswith("/git/blobs/stable-sha")
