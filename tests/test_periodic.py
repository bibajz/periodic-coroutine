import asyncio
from typing import NoReturn

import pytest

from pytest_asyncio.plugin import event_loop

from periodic_coroutine import Periodic


async def awake_msg() -> str:
    await asyncio.sleep(0.5)
    return "Good Morning!"


async def just_raise() -> NoReturn:
    await asyncio.sleep(0.1)
    raise ValueError("Not a case of asyncio.CancelledError or asyncio.TimeoutError")


@pytest.mark.asyncio
async def test_interval_is_longer_than_blocking(event_loop):
    """
    *awake_msg* blocks for 0.5 seconds, which is a shorter time than the 2sec period -
    everything should proceed fine
    """
    p = Periodic(awake_msg, 2.0)
    event_loop.call_soon(p.start)
    await asyncio.sleep(0.01)  # Yielding control to the loop is necessary to start

    res = await p.get_result()
    assert res == "Good Morning!"

    event_loop.call_soon(p.stop)
    await asyncio.sleep(0.01)  # Yielding control to the loop is necessary to end


@pytest.mark.asyncio
async def test_interval_is_shorter_than_blocking_without_ignore(event_loop):
    """
    *awake_msg* blocks for 0.5 seconds, which is a longer time than the 0.2sec period -
    if we choose not to ignore exceptions (default), *Periodic* will raise raise
    an *AttributeError* since _result is not set (and never will be).
    """
    p = Periodic(awake_msg, 0.2)
    event_loop.call_soon(p.start)
    await asyncio.sleep(0.01)  # Yielding control to the loop is necessary to start

    with pytest.raises(AttributeError):
        await p.get_result()

    event_loop.call_soon(p.stop)
    await asyncio.sleep(0.01)  # Yielding control to the loop is necessary to end


@pytest.mark.asyncio
async def test_interval_is_shorter_than_blocking_without_ignore(event_loop):
    """
    *awake_msg* blocks for 0.5 seconds, which is a longer time than the 0.2sec period -
    if we choose to ignore exceptions, *Periodic* will chugg along, although always
    cancelling the task and awaiting *get_result* will result in a sentinel value
    """
    p = Periodic(awake_msg, 0.2, ignore_exceptions=True)
    event_loop.call_soon(p.start)
    await asyncio.sleep(0.01)  # Yielding control to the loop is necessary to start

    res = await p.get_result()
    assert res is not None  # Chuggs along, with nothing meaningful as a result

    assert p._main in asyncio.all_tasks(event_loop)  # Periodic is still running
    assert p.running

    event_loop.call_soon(p.stop)
    await asyncio.sleep(0.01)  # Yielding control to the loop is necessary to end


@pytest.mark.asyncio
async def test_coroutine_throws_unhandled_exception(event_loop):
    """
    Let the coroutine throw an exception which is not handled - this affects the inner
    task and also the main task.

    This test serves as a reminder that coroutine and its error handling are tightly
    coupled and to have a robust periodic scheduling mechanism, one needs to design it
    more carefully...
    """
    p = Periodic(just_raise, 1, ignore_exceptions=False)
    event_loop.call_soon(p.start)
    await asyncio.sleep(0.01)  # Yielding control to the loop is necessary to start

    with pytest.raises(ValueError):
        await p._task

    await asyncio.sleep(1.5)  # Wait for any necessary clean-up

    assert p._main not in asyncio.all_tasks(event_loop)  # Periodic is NOT running...
    assert p.running  # ...but the state was not switched because of the exception
    assert len(asyncio.all_tasks()) == 1  # Only the test coroutine is running

    event_loop.call_soon(p.stop)
    await asyncio.sleep(0.01)  # Yielding control to the loop is necessary to end
