import asyncio

import pytest


@pytest.fixture(autouse=True)
async def _cancel_leftover_tasks():
    """
    The in-process MUCA-Server (and its conversations) leaves background
    tasks behind; cancel them before the test's event loop goes away.
    """

    yield

    current = asyncio.current_task()
    leftover = [
        task
        for task in asyncio.all_tasks()
        if task is not current and not task.done()
    ]

    for task in leftover:
        task.cancel()

    await asyncio.gather(*leftover, return_exceptions=True)
