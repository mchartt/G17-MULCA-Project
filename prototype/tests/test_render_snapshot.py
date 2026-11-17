"""
deploy/render/snapshot.py: /data saved to one blob and brought back at the
next start. A small local HTTP server stands in for Azure Blob Storage.
"""

from __future__ import annotations

import importlib.util
import io
import sqlite3
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "deploy" / "render" / "snapshot.py"
_spec = importlib.util.spec_from_file_location("render_snapshot", _PATH)
snapshot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snapshot)

TOKEN = "sv=2021&sig=VERY-SECRET"


class Blob:
    """One blob: PUT stores it, GET returns it or 404. `fail` makes every request answer that status."""

    def __init__(self) -> None:
        self.body: bytes | None = None
        self.puts: list[dict] = []
        self.fail: int | None = None
        blob = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _answer(self, status: int, body: bytes = b"") -> None:
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if blob.fail:
                    self._answer(blob.fail)
                elif blob.body is None:
                    self._answer(404)
                else:
                    self._answer(200, blob.body)

            def do_PUT(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                if blob.fail:
                    self._answer(blob.fail)
                    return
                blob.puts.append({k.lower(): v for k, v in self.headers.items()})
                blob.body = body
                self._answer(201)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/cadence/data.tar.gz?{TOKEN}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def blob():
    b = Blob()
    yield b
    b.close()


def make_data(root: Path) -> Path:
    """A data folder like the container's: a database still open in WAL mode, and a plain file."""
    data = root / "data"
    (data / "muca").mkdir(parents=True)
    db = sqlite3.connect(data / "web.sqlite3")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE web_user (email TEXT)")
    db.execute("INSERT INTO web_user VALUES ('ada@example.org')")
    db.commit()  # stays open: the row is still in the -wal file
    (data / "muca" / "_runtime_config.json").write_text('{"model": "x"}')
    return data, db


def test_a_save_then_a_restore_brings_every_file_back(tmp_path, blob):
    data, db = make_data(tmp_path)
    assert (data / "web.sqlite3-wal").exists()
    snapshot.save(blob.url, data)
    db.close()

    fresh = tmp_path / "fresh"
    assert snapshot.restore(blob.url, fresh) is True
    restored = sqlite3.connect(fresh / "web.sqlite3")
    assert restored.execute("SELECT email FROM web_user").fetchall() == [("ada@example.org",)]
    restored.close()
    assert (fresh / "muca" / "_runtime_config.json").read_text() == '{"model": "x"}'
    # SQLite's side files are not copied: the backup already holds their rows.
    assert sorted(p.name for p in fresh.rglob("*") if p.is_file()) == ["_runtime_config.json", "web.sqlite3"]
    assert blob.puts[0]["x-ms-blob-type"] == "BlockBlob"


def test_the_first_start_has_no_snapshot_and_starts_empty(tmp_path, blob):
    assert snapshot.restore(blob.url, tmp_path / "data") is False
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("status", [403, 500])
def test_a_snapshot_that_cannot_be_read_stops_the_start(tmp_path, blob, status, monkeypatch):
    """Starting empty here would let the next save replace the real snapshot with nothing."""
    blob.fail = status
    with pytest.raises(snapshot.SnapshotError):
        snapshot.restore(blob.url, tmp_path / "data")
    monkeypatch.setenv("CADENCE_SNAPSHOT_URL", blob.url)
    monkeypatch.setenv("CADENCE_DATA_DIR", str(tmp_path / "data"))
    assert snapshot.main(["snapshot.py", "restore"]) == 1


def test_a_damaged_snapshot_stops_the_start(tmp_path, blob):
    blob.body = b"not a tar file"
    with pytest.raises(snapshot.SnapshotError):
        snapshot.restore(blob.url, tmp_path / "data")


def test_a_snapshot_cannot_write_outside_the_data_folder(tmp_path, blob):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo("../escaped.txt")
        info.size = 2
        tar.addfile(info, io.BytesIO(b"hi"))
    blob.body = buffer.getvalue()
    with pytest.raises(snapshot.SnapshotError):
        snapshot.restore(blob.url, tmp_path / "data")
    assert not (tmp_path / "escaped.txt").exists()


def test_the_token_never_reaches_a_log_or_an_error(tmp_path, blob, caplog):
    data, db = make_data(tmp_path)
    db.close()
    with caplog.at_level("INFO", logger="snapshot"):
        snapshot.save(blob.url, data)
        blob.fail = 403
        with pytest.raises(snapshot.SnapshotError) as refused:
            snapshot.save(blob.url, data)
    assert "SECRET" not in caplog.text and "SECRET" not in str(refused.value)
    assert "/cadence/data.tar.gz" in caplog.text


def test_watch_saves_only_when_something_changed_and_once_more_on_stop(tmp_path, blob):
    data, db = make_data(tmp_path)
    stop = threading.Event()
    watcher = threading.Thread(target=snapshot.watch, args=(blob.url, data, 0.05, stop))
    watcher.start()
    try:
        threading.Event().wait(0.3)
        assert blob.puts == []  # nothing changed since the start
        db.execute("INSERT INTO web_user VALUES ('bruno@example.org')")
        db.commit()
        for _ in range(100):
            if blob.puts:
                break
            threading.Event().wait(0.05)
        assert len(blob.puts) >= 1
        saved = len(blob.puts)
        (data / "muca" / "late.json").write_text("{}")  # written just before the stop
    finally:
        stop.set()
        watcher.join(timeout=5)
        db.close()
    assert not watcher.is_alive()
    assert len(blob.puts) > saved
    fresh = tmp_path / "fresh"
    snapshot.restore(blob.url, fresh)
    assert (fresh / "muca" / "late.json").exists()


def test_a_failed_save_is_tried_again_at_the_next_round(tmp_path, blob):
    data, db = make_data(tmp_path)
    db.close()
    blob.fail = 500
    stop = threading.Event()
    watcher = threading.Thread(target=snapshot.watch, args=(blob.url, data, 0.05, stop))
    watcher.start()
    try:
        threading.Event().wait(0.3)  # the watcher has taken its starting picture
        (data / "muca" / "new.json").write_text("{}")
        threading.Event().wait(0.3)  # at least one save was refused
        assert blob.puts == []
        blob.fail = None
        for _ in range(100):
            if blob.puts:
                break
            threading.Event().wait(0.05)
    finally:
        stop.set()
        watcher.join(timeout=5)
    assert blob.puts


def test_without_the_address_nothing_runs(monkeypatch):
    monkeypatch.delenv("CADENCE_SNAPSHOT_URL", raising=False)
    assert snapshot.main(["snapshot.py", "restore"]) == 0
    assert snapshot.main(["snapshot.py", "watch"]) == 0
    assert snapshot.main(["snapshot.py", "dance"]) == 2
