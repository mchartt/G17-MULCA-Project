"""
Keeps /data across restarts on a host without a disk (Render free plan).

Everything Cadence remembers is SQLite files under /data: accounts and spaces
(web.sqlite3), each group's chat memory and project state (muca/*.db), the
Discord bot's links (mulca.db). Render's free plan empties /data at every
restart, redeploy and sleep. This script copies /data to ONE blob in Azure
Blob Storage and brings it back at the next start:

    python snapshot.py restore   at start, before the servers open the files
    python snapshot.py watch     while running: save every few minutes when
                                 something changed, and once more on SIGTERM
    python snapshot.py save      one save now (by hand)

Off unless CADENCE_SNAPSHOT_URL is set: then nothing here runs and the
container behaves as before.

    CADENCE_SNAPSHOT_URL      the blob's full address with its SAS token, e.g.
                              https://<account>.blob.core.windows.net/cadence/data.tar.gz?sv=...
                              The token needs read, create and write. It is a
                              secret: it is never logged.
    CADENCE_SNAPSHOT_SECONDS  seconds between saves, default 120
    CADENCE_DATA_DIR          default /data

What it does not promise: a change made after the last save and before a
hard kill is lost (at most CADENCE_SNAPSHOT_SECONDS). Two containers writing
the same blob would overwrite each other; Render free runs one.

Only the standard library, so the image needs nothing new.
"""

from __future__ import annotations

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
from urllib.parse import urlsplit

logger = logging.getLogger("snapshot")

SQLITE_MAGIC = b"SQLite format 3\x00"
# Written by SQLite next to a database while it is open: the backup below
# already contains what they hold.
SIDE_FILES = ("-wal", "-shm", "-journal")
TIMEOUT_SECONDS = 60
AZURE_API_VERSION = "2021-08-06"


class SnapshotError(RuntimeError):
    """A snapshot that exists could not be read, or a save was refused."""


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


def restore(url: str, data_dir: Path) -> bool:
    """
    Bring the last snapshot back. False when there is none yet (first start).
    Raises SnapshotError when a snapshot may exist but cannot be read: the
    caller must then NOT start, or the next save would replace it with nothing.
    """
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=TIMEOUT_SECONDS) as response:
            archive = response.read()
    except urllib.error.HTTPError as exc:
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


def save(url: str, data_dir: Path) -> int:
    """Upload /data as it is now. Returns the size sent, in bytes."""
    archive = pack(data_dir)
    request = urllib.request.Request(
        url,
        data=archive,
        method="PUT",
        headers={
            "x-ms-blob-type": "BlockBlob",
            "x-ms-version": AZURE_API_VERSION,
            "Content-Type": "application/gzip",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):
            pass
    except urllib.error.HTTPError as exc:
        raise SnapshotError(f"saving to {where(url)} answered {exc.code}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise SnapshotError(f"could not reach {where(url)}: {getattr(exc, 'reason', exc)}") from None
    logger.info("saved %d kB to %s", len(archive) // 1024, where(url))
    return len(archive)


def watch(url: str, data_dir: Path, every: float, stop: threading.Event) -> None:
    """Save when something changed, every `every` seconds, and once more when asked to stop."""
    last = fingerprint(data_dir)  # what restore just wrote: nothing new to save yet
    while True:
        stopping = stop.wait(every)
        now = fingerprint(data_dir)
        if now != last:
            try:
                save(url, data_dir)
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
    try:
        if command == "restore":
            restore(url, data_dir)
        elif command == "save":
            save(url, data_dir)
        else:
            stop = threading.Event()
            for signum in (signal.SIGTERM, signal.SIGINT):
                signal.signal(signum, lambda *_: stop.set())
            watch(url, data_dir, float(os.environ.get("CADENCE_SNAPSHOT_SECONDS", "120")), stop)
    except SnapshotError as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
