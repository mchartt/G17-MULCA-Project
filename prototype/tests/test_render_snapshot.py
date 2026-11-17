"""
deploy/render/snapshot.py: /data saved to one blob and brought back at the
next start. A small local HTTP server stands in for the object store: Azure
Blob Storage (a token in the address) or Supabase Storage's S3 endpoint
(every request signed with an S3 access key).
"""

from __future__ import annotations

import datetime
import hashlib
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
        # S3 mode: only requests signed by this access key id are accepted,
        # and a body must match the hash that was signed.
        self.key_id: str | None = None
        self.no_bucket = False
        blob = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _answer(self, status: int, body: bytes = b"") -> None:
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _signed(self, body: bytes) -> bool:
                if blob.key_id is None:
                    return True
                return (
                    f"Credential={blob.key_id}/" in self.headers.get("Authorization", "")
                    and self.headers.get("x-amz-content-sha256") == hashlib.sha256(body).hexdigest()
                    and bool(self.headers.get("x-amz-date"))
                )

            def do_GET(self):
                if blob.fail:
                    self._answer(blob.fail)
                elif not self._signed(b""):
                    self._answer(403, b"<Error><Code>SignatureDoesNotMatch</Code></Error>")
                elif blob.no_bucket:
                    self._answer(404, b"<Error><Code>NoSuchBucket</Code><Message>Bucket not found</Message></Error>")
                elif blob.body is None:
                    self._answer(404, b"<Error><Code>NoSuchKey</Code></Error>")
                else:
                    self._answer(200, blob.body)

            def do_PUT(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                if blob.fail:
                    self._answer(blob.fail)
                    return
                if not self._signed(body):
                    self._answer(403, b"<Error><Code>SignatureDoesNotMatch</Code></Error>")
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


# ---------------------------------------------------------------------------
# Supabase Storage (S3 endpoint): requests signed with an S3 access key
# ---------------------------------------------------------------------------

KEY = snapshot.S3Key("AKIDEXAMPLE", "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY", "eu-central-1")


@pytest.mark.parametrize(
    "method, url, body, signature",
    [
        ("GET", "https://abcd1234.storage.supabase.co/storage/v1/s3/cadence/data.tar.gz", b"",
         "2280cd084ad6b754962bf5901cd52318a833d457922b8c8521d2d94af52dd5a1"),
        ("PUT", "https://abcd1234.storage.supabase.co/storage/v1/s3/cadence/data.tar.gz", b"hello snapshot",
         "66a784405210227b019149cef6316d13b09a154cceff847026e76b01477c329a"),
        ("PUT", "http://127.0.0.1:9000/storage/v1/s3/bucket/dir/data-v2.tar.gz", b"x" * 5000,
         "838728a776fa106f4d5a70dca1deac111898c3e4624864217a8e11b75158b8a6"),
    ],
)
def test_the_signature_is_the_one_the_aws_sdk_computes(method, url, body, signature):
    """
    The expected values were produced by botocore's S3SigV4Auth for the same
    key, time, address and body (17 Nov 2026). The SDK is not a dependency:
    these fixed values keep our own signing honest.
    """
    now = datetime.datetime(2026, 11, 17, 16, 5, 9, tzinfo=datetime.timezone.utc)
    headers = snapshot.s3_headers(KEY, method, url, body, now=now)
    assert headers["x-amz-date"] == "20261117T160509Z"
    assert headers["x-amz-content-sha256"] == hashlib.sha256(body).hexdigest()
    assert headers["Authorization"] == (
        "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20261117/eu-central-1/s3/aws4_request, "
        f"SignedHeaders=host;x-amz-content-sha256;x-amz-date, Signature={signature}"
    )


def s3_blob(blob):
    blob.key_id = KEY.key_id
    return blob.url.split("?")[0]  # no token in the address: the key signs the request


def test_with_an_s3_key_a_save_then_a_restore_brings_every_file_back(tmp_path, blob):
    url = s3_blob(blob)
    data, db = make_data(tmp_path)
    assert snapshot.restore(url, tmp_path / "first", KEY) is False  # first start: no snapshot yet
    snapshot.save(url, data, KEY)
    db.close()
    assert "x-ms-blob-type" not in blob.puts[0]  # not Azure's way
    fresh = tmp_path / "fresh"
    assert snapshot.restore(url, fresh, KEY) is True
    restored = sqlite3.connect(fresh / "web.sqlite3")
    assert restored.execute("SELECT email FROM web_user").fetchall() == [("ada@example.org",)]
    restored.close()


def test_without_the_key_the_store_refuses_and_the_start_stops(tmp_path, blob):
    url = s3_blob(blob)
    data, db = make_data(tmp_path)
    db.close()
    with pytest.raises(snapshot.SnapshotError):
        snapshot.save(url, data)  # unsigned
    with pytest.raises(snapshot.SnapshotError):
        snapshot.restore(url, tmp_path / "fresh", snapshot.S3Key("SOMEONE-ELSE", "x", "eu-central-1"))
    assert blob.puts == []


def test_a_bucket_that_does_not_exist_stops_the_start(tmp_path, blob):
    """Starting anyway would hide that every save is going to fail."""
    url = s3_blob(blob)
    blob.no_bucket = True
    with pytest.raises(snapshot.SnapshotError, match="bucket"):
        snapshot.restore(url, tmp_path / "data", KEY)


def test_the_key_comes_from_the_environment_whole_or_not_at_all(tmp_path, blob, monkeypatch, caplog):
    url = s3_blob(blob)
    data, db = make_data(tmp_path)
    db.close()
    monkeypatch.setenv("CADENCE_SNAPSHOT_URL", url)
    monkeypatch.setenv("CADENCE_DATA_DIR", str(data))
    monkeypatch.setenv("CADENCE_SNAPSHOT_KEY_ID", KEY.key_id)
    assert snapshot.main(["snapshot.py", "save"]) == 1  # the secret and the region are missing
    assert blob.puts == []
    monkeypatch.setenv("CADENCE_SNAPSHOT_SECRET", KEY.secret)
    monkeypatch.setenv("CADENCE_SNAPSHOT_REGION", KEY.region)
    with caplog.at_level("INFO", logger="snapshot"):
        assert snapshot.main(["snapshot.py", "save"]) == 0
        assert snapshot.main(["snapshot.py", "restore"]) == 0
    assert len(blob.puts) == 1
    assert KEY.secret not in caplog.text
