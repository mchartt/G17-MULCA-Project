"""Fixtures of the cross-channel end-to-end suite (harness.py, LIVE_TESTS.md)."""

from __future__ import annotations

import pytest

from .harness import Group, Stack, mode


def pytest_report_header(config):
    return f"cross-channel e2e: {mode()}"


@pytest.fixture
async def stack(tmp_path):
    started = await Stack(tmp_path).start()
    yield started
    await started.stop()


@pytest.fixture
async def group(stack):
    """A web space (Ada and Bruno) with a Discord and a Slack channel linked by pasting its invite link."""
    made = Group(stack)
    try:
        await made.linked()
        yield made
    finally:
        await made.close()


@pytest.fixture
async def bare(stack):
    """A group with nothing linked yet: each test builds what it needs."""
    made = Group(stack)
    yield made
    await made.close()
