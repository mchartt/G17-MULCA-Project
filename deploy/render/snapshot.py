"""
Keeps /data across restarts on a host without a disk (Render free plan).

Everything Cadence remembers is SQLite files under /data: accounts and spaces
(web.sqlite3), each group's chat memory and project state (muca/*.db), the
Discord bot's links (mulca.db). Render's free plan empties /data at every
restart, redeploy and sleep. This script copies /data to ONE file in an object
store (Supabase Storage, or Azure Blob Storage) and brings it back at the
next start:

    python snapshot.py restore   at start, before the servers open the files
    python snapshot.py watch     while running: save every few minutes when
                                 something changed, and once more on SIGTERM
    python snapshot.py save      one save now (by hand)

Off unless CADENCE_SNAPSHOT_URL is set: then nothing here runs and the
container behaves as before.

Two stores, chosen by which variables are set:

  Supabase Storage (or any S3-compatible store), signed with an S3 access key:
    CADENCE_SNAPSHOT_URL      the file's address on the S3 endpoint, e.g.
                              https://<project>.storage.supabase.co/storage/v1/s3/cadence/data.tar.gz
                              (.../s3/<bucket>/<file name>)
    CADENCE_SNAPSHOT_KEY_ID   the S3 access key id (Supabase: Storage > S3 > access keys)
    CADENCE_SNAPSHOT_SECRET   its secret access key. A secret: never logged.
    CADENCE_SNAPSHOT_REGION   the region shown next to the endpoint, e.g. eu-central-1

  Azure Blob Storage, with a SAS token in the address (no key variables):
    CADENCE_SNAPSHOT_URL      https://<account>.blob.core.windows.net/cadence/data.tar.gz?sv=...
                              The token needs read, create and write. The whole
                              address is then a secret: it is never logged.

    CADENCE_SNAPSHOT_SECONDS  seconds between saves, default 120
    CADENCE_DATA_DIR          default /data

What it does not promise: a change made after the last save and before a
hard kill is lost (at most CADENCE_SNAPSHOT_SECONDS). Two containers writing
the same blob would overwrite each other; Render free runs one.

Only the standard library, so the image needs nothing new.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import io
import logging
import os
import signal
import sqlite3
import sys
import tarfile
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple
from urllib.parse import quote, urlsplit

logger = logging.getLogger("snapshot")

SQLITE_MAGIC = b"SQLite format 3\x00"
# Written by SQLite next to a database while it is open: the backup below
# already contains what they hold.
SIDE_FILES = ("-wal", "-shm", "-journal")
TIMEOUT_SECONDS = 60
AZURE_API_VERSION = "2021-08-06"


class SnapshotError(RuntimeError):
    """A snapshot that exists could not be read, or a save was refused."""


class S3Key(NamedTuple):
    """An S3 access key: every request is signed with it (AWS Signature Version 4)."""

    key_id: str
    secret: str
    region: str


def s3_headers(key: S3Key, method: str, url: str, body: bytes, *, now: datetime.datetime | None = None) -> dict[str, str]:
    """
    The headers that sign one S3 request (AWS Signature Version 4, service
    "s3"). Written here with the standard library so the image needs no SDK.
    Only the host, the date and the body's hash are signed: any other header
    the caller adds travels unsigned, which S3 allows.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    day = stamp[:8]
    parts = urlsplit(url)
    body_hash = hashlib.sha256(body).hexdigest()
    signed = "host;x-amz-content-sha256;x-amz-date"
    canonical = "\n".join([
        method,
        quote(parts.path or "/", safe="/-_.~"),
        "",  # no query string
        f"host:{parts.netloc}",
        f"x-amz-content-sha256:{body_hash}",
        f"x-amz-date:{stamp}",
        "",
        signed,
        body_hash,
    ])
    scope = f"{day}/{key.region}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()])

    def mac(secret: bytes, text: str) -> bytes:
        return hmac.new(secret, text.encode(), hashlib.sha256).digest()

    signing_key = mac(mac(mac(mac(("AWS4" + key.secret).encode(), day), key.region), "s3"), "aws4_request")
    signature = hmac.new(signing_key, to_sign.encode(), hashlib.sha256).hexdigest()
    return {
        "x-amz-date": stamp,
        "x-amz-content-sha256": body_hash,
        "Authorization": f"AWS4-HMAC-SHA256 Credential={key.key_id}/{scope}, SignedHeaders={signed}, Signature={signature}",
    }


def where(url: str) -> str:
    """The blob's address without its token, safe to log."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def fingerprint(data_dir: Path) -> tuple:
    """Changes whenever a file under data_dir is added, removed or written."""
    seen = []
    for path in sorted(data_dir.rglob("*")):
        if path.is_file():
            stat = path.stat()
            seen.append((str(path.relative_to(data_dir)), stat.st_size, stat.st_mtime_ns))
    return tuple(seen)


def pack(data_dir: Path) -> bytes:
    """
    /data as a .tar.gz. A SQLite file is copied with SQLite's own backup, so
    the copy is consistent even while a server is writing to it.
    """
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar, tempfile.TemporaryDirectory() as tmp:
        for path in sorted(data_dir.rglob("*")):
            if not path.is_file() or path.name.endswith(SIDE_FILES):
                continue
            name = str(path.relative_to(data_dir))
            if _is_sqlite(path):
                copy = Path(tmp) / "copy.db"
                copy.unlink(missing_ok=True)
                source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                target = sqlite3.connect(copy)
                try:
                    source.backup(target)
                finally:
                    target.close()
                    source.close()
                tar.add(copy, arcname=name)
            else:
                tar.add(path, arcname=name)
    return buffer.getvalue()


def unpack(archive: bytes, data_dir: Path) -> int:
    """Extract into data_dir; returns how many files. Refuses paths that leave it."""
    data_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        members = [m for m in tar.getmembers() if m.isfile()]
        try:
            tar.extractall(data_dir, members=members, filter="data")
        except tarfile.FilterError as exc:
            raise SnapshotError(f"the snapshot holds a path outside the data folder: {exc}") from None
    return len(members)


def restore(url: str, data_dir: Path, key: S3Key | None = None) -> bool:
    """
    Bring the last snapshot back. False when there is none yet (first start).
    Raises SnapshotError when a snapshot may exist but cannot be read: the
    caller must then NOT start, or the next save would replace it with nothing.
    A bucket that does not exist is an error too: every save would fail, and
    starting anyway would hide that nothing is being kept.
    """
    headers = s3_headers(key, "GET", url, b"") if key else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT_SECONDS) as response:
            archive = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and b"NoSuchBucket" in exc.read(2000):
            raise SnapshotError(f"the bucket of {where(url)} does not exist: create it, or fix the address") from None
        if exc.code == 404:
            logger.info("no snapshot yet at %s: starting empty", where(url))
            return False
        raise SnapshotError(f"reading {where(url)} answered {exc.code}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise SnapshotError(f"could not reach {where(url)}: {getattr(exc, 'reason', exc)}") from None
    try:
        count = unpack(archive, data_dir)
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise SnapshotError(f"the snapshot at {where(url)} is not readable: {exc}") from None
    logger.info("restored %d files (%d kB) from %s", count, len(archive) // 1024, where(url))
    return True


def save(url: str, data_dir: Path, key: S3Key | None = None) -> int:
    """Upload /data as it is now, replacing the last snapshot. Returns the size sent, in bytes."""
    archive = pack(data_dir)
    headers = {"Content-Type": "application/gzip"}
    if key:
        headers.update(s3_headers(key, "PUT", url, archive))
    else:  # Azure Blob Storage: the SAS token in the address is the permission
        headers.update({"x-ms-blob-type": "BlockBlob", "x-ms-version": AZURE_API_VERSION})
    request = urllib.request.Request(url, data=archive, method="PUT", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):
            pass
    except urllib.error.HTTPError as exc:
        raise SnapshotError(f"saving to {where(url)} answered {exc.code}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise SnapshotError(f"could not reach {where(url)}: {getattr(exc, 'reason', exc)}") from None
    logger.info("saved %d kB to %s", len(archive) // 1024, where(url))
    return len(archive)


def watch(url: str, data_dir: Path, every: float, stop: threading.Event, key: S3Key | None = None) -> None:
    """Save when something changed, every `every` seconds, and once more when asked to stop."""
    last = fingerprint(data_dir)  # what restore just wrote: nothing new to save yet
    while True:
        stopping = stop.wait(every)
        now = fingerprint(data_dir)
        if now != last:
            try:
                save(url, data_dir, key)
                last = now
            except SnapshotError as exc:  # keep running: the next round tries again
                logger.error("%s", exc)
        if stopping:
            return


def _is_sqlite(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(len(SQLITE_MAGIC)) == SQLITE_MAGIC


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="snapshot: %(message)s")
    url = os.environ.get("CADENCE_SNAPSHOT_URL", "").strip()
    data_dir = Path(os.environ.get("CADENCE_DATA_DIR", "/data"))
    command = argv[1] if len(argv) > 1 else ""
    if command not in ("restore", "save", "watch"):
        print("usage: snapshot.py restore | save | watch", file=sys.stderr)
        return 2
    if not url:
        logger.info("CADENCE_SNAPSHOT_URL is not set: nothing to do")
        return 0
    key_id = os.environ.get("CADENCE_SNAPSHOT_KEY_ID", "").strip()
    secret = os.environ.get("CADENCE_SNAPSHOT_SECRET", "").strip()
    region = os.environ.get("CADENCE_SNAPSHOT_REGION", "").strip()
    key = None
    if key_id or secret or region:
        if not (key_id and secret and region):
            logger.error("set CADENCE_SNAPSHOT_KEY_ID, CADENCE_SNAPSHOT_SECRET and CADENCE_SNAPSHOT_REGION together")
            return 1
        key = S3Key(key_id, secret, region)
    try:
        if command == "restore":
            restore(url, data_dir, key)
        elif command == "save":
            save(url, data_dir, key)
        else:
            stop = threading.Event()
            for signum in (signal.SIGTERM, signal.SIGINT):
                signal.signal(signum, lambda *_: stop.set())
            watch(url, data_dir, float(os.environ.get("CADENCE_SNAPSHOT_SECONDS", "120")), stop, key)
    except SnapshotError as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
