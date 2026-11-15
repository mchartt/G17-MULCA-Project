"""
Two processes sharing one bot account both answer every message -- this is
what stops a second one from starting by mistake (found live: exactly this
happened after a manual restart left an old process running).
"""

import os
import threading
import time

import pytest

from mulca_discord.singleton import (
    LOCK_PORT_ENV_VAR,
    AlreadyRunning,
    acquire_singleton_lock,
)


@pytest.fixture(autouse=True)
def _distinct_test_port(monkeypatch):
    # A fixed port shared with a real deployment would make this test flaky
    # (and would refuse to run at all if a real instance happens to be up).
    monkeypatch.setenv(LOCK_PORT_ENV_VAR, "47999")


def test_the_first_process_acquires_the_lock():
    lock = acquire_singleton_lock()
    try:
        assert lock is not None
    finally:
        lock.close()


def test_a_second_process_is_refused_once_retrying_runs_out():
    first = acquire_singleton_lock()
    try:
        with pytest.raises(AlreadyRunning):
            # A short deadline: this is testing the "still genuinely taken"
            # outcome, not asking the test to wait out the real default.
            acquire_singleton_lock(retry_deadline_seconds=0.2)
    finally:
        first.close()


def test_the_lock_is_free_again_once_the_holder_closes_it():
    first = acquire_singleton_lock()
    first.close()

    second = acquire_singleton_lock()
    second.close()


def test_a_slow_release_is_waited_out_instead_of_refused():
    """
    A Ctrl+C'd process can take a few seconds to actually exit; restarting
    in that window should succeed once the old one actually lets go, not
    bounce off immediately.
    """

    first = acquire_singleton_lock()

    def release_shortly() -> None:
        time.sleep(0.2)
        first.close()

    threading.Thread(target=release_shortly).start()

    second = acquire_singleton_lock(retry_deadline_seconds=2.0)
    second.close()
