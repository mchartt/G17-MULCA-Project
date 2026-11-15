"""
Stops a second `mulca_discord` process from running against the same bot
account by mistake.

Discord itself won't catch this: a bot token can have more than one live
gateway connection at once, and both receive every event -- so two
processes both forwarding the same Discord message to MUCA-Server means two
independent replies to it, not an error from anywhere. Found live: a second
process left running from an earlier restart caused every message to get
answered twice.

Mechanism: bind a fixed localhost TCP port for the life of the process. The
OS enforces "only one owner" and releases it automatically if the process
dies or crashes -- no stale lock file to clean up, and no extra dependency.
"""

from __future__ import annotations

import logging
import os
import socket
import time

logger = logging.getLogger(__name__)

# Arbitrary, just needs to not collide with anything else on the box;
# overridable in case it ever does. Distinct from MUCA_SERVER_PORT, since
# this locks the Discord adapter, not the cognition server.
DEFAULT_LOCK_PORT = 47821
LOCK_PORT_ENV_VAR = "MULCA_DISCORD_LOCK_PORT"

# A Ctrl+C'd process can take a few real seconds to actually exit --
# discord.py's own shutdown (disconnecting voice, closing the gateway and
# HTTP session) isn't instant. Without retrying, a restart attempted in
# that window gets refused even though the old process is on its way out
# anyway, forcing a manual wait-and-retry. Retrying here instead means a
# normal "stop, then immediately start again" just works.
RETRY_DEADLINE_SECONDS = 10.0
RETRY_INTERVAL_SECONDS = 0.5


class AlreadyRunning(RuntimeError):
    """Another mulca_discord process still holds the singleton lock after waiting."""


def acquire_singleton_lock(
    *,
    retry_deadline_seconds: float = RETRY_DEADLINE_SECONDS,
) -> socket.socket:
    """
    Claims the lock for this process's lifetime.

    Returns the bound socket -- callers must keep a reference to it for as
    long as the process runs (letting it get garbage-collected releases the
    lock early). Raises AlreadyRunning only if the port is still taken after
    retrying for retry_deadline_seconds -- a still-shutting-down previous
    process, not a genuinely concurrent one, is the common case this waits
    out.
    """

    port = int(os.environ.get(LOCK_PORT_ENV_VAR, DEFAULT_LOCK_PORT))
    deadline = time.monotonic() + retry_deadline_seconds
    last_error: OSError | None = None
    logged_waiting = False

    while True:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            lock_socket.bind(("127.0.0.1", port))
            return lock_socket
        except OSError as exc:
            lock_socket.close()
            last_error = exc

        if time.monotonic() >= deadline:
            break

        if not logged_waiting:
            # Once, not every retry -- otherwise this is silent for up to
            # retry_deadline_seconds, which looks indistinguishable from
            # actually being stuck.
            logger.info(
                "Port %d is still held; waiting up to %.0fs for the "
                "previous process to finish exiting...",
                port,
                retry_deadline_seconds,
            )
            logged_waiting = True

        time.sleep(RETRY_INTERVAL_SECONDS)

    raise AlreadyRunning(
        f"Another mulca_discord process still appears to be running after "
        f"waiting {retry_deadline_seconds:.0f}s (port {port} is taken). Two "
        f"processes sharing one bot account both answer every message, so "
        f"this refuses to start rather than risk that. Stop the other "
        f"process first, or set {LOCK_PORT_ENV_VAR} if this is a deliberate "
        f"second instance on its own bot account."
    ) from last_error
