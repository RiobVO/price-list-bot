"""Тест graceful shutdown: refresh-task отменён и дождан, сессия бота закрыта."""

from __future__ import annotations

import asyncio

import pytest

from src.main import shutdown


@pytest.mark.asyncio
async def test_shutdown_cancels_task_and_closes_bot() -> None:
    async def forever() -> None:
        await asyncio.Event().wait()  # никогда не завершается

    task = asyncio.create_task(forever())
    await asyncio.sleep(0)  # дать задаче стартовать

    class FakeBot:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    bot = FakeBot()
    await shutdown(task, bot)  # type: ignore[arg-type]
    assert task.cancelled()
    assert bot.closed
