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

import os
import socket

# Arbitrary, just needs to not collide with anything else on the box;
# overridable in case it ever does. Distinct from MUCA_SERVER_PORT, since
# this locks the Discord adapter, not the cognition server.
DEFAULT_LOCK_PORT = 47821
LOCK_PORT_ENV_VAR = "MULCA_DISCORD_LOCK_PORT"


class AlreadyRunning(RuntimeError):
    """Another mulca_discord process already holds the singleton lock."""


def acquire_singleton_lock() -> socket.socket:
    """
    Claims the lock for this process's lifetime.

    Returns the bound socket -- callers must keep a reference to it for as
    long as the process runs (letting it get garbage-collected releases the
    lock early). Raises AlreadyRunning if another process already holds it.
    """

    port = int(os.environ.get(LOCK_PORT_ENV_VAR, DEFAULT_LOCK_PORT))
    lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        lock_socket.bind(("127.0.0.1", port))
    except OSError as exc:
        lock_socket.close()
        raise AlreadyRunning(
            f"Another mulca_discord process already appears to be running "
            f"(port {port} is taken). Two processes sharing one bot "
            f"account both answer every message, so this refuses to start "
            f"rather than risk that. Stop the other process first, or set "
            f"{LOCK_PORT_ENV_VAR} if this is a deliberate second instance "
            f"on its own bot account."
        ) from exc

    return lock_socket
