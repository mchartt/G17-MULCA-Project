"""
Two processes sharing one bot account both answer every message -- this is
what stops a second one from starting by mistake (found live: exactly this
happened after a manual restart left an old process running).
"""

import os

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


def test_a_second_process_is_refused_while_the_first_holds_it():
    first = acquire_singleton_lock()
    try:
        with pytest.raises(AlreadyRunning):
            acquire_singleton_lock()
    finally:
        first.close()


def test_the_lock_is_free_again_once_the_holder_closes_it():
    first = acquire_singleton_lock()
    first.close()

    second = acquire_singleton_lock()
    second.close()
