import asyncio
import itertools
from contextlib import suppress
from typing import Any, Awaitable, Callable, Optional, TypeVar

__all__ = [
    "Periodic",
]

RType = TypeVar("RType")
Loop = Optional[asyncio.AbstractEventLoop]


class Periodic:
    __slots__ = (
        "_coro",
        "_args",
        "_kwargs",
        "_loop",
        "_lock",
        "_context_manager",
        "_interval",
        "_running",
        "_result",
        "_task",
        "_main",
    )

    def __init__(
        self,
        coro: Callable[..., Awaitable[RType]],
        interval: float,
        *args: Any,
        loop: Loop = None,
        ignore_exceptions: bool = False,
        **kwargs: Any,
    ) -> None:
        self._coro = coro
        self._args = list(args)
        self._kwargs = dict(kwargs)
        self._loop = loop or asyncio.get_running_loop()
        self._lock = asyncio.Lock()
        self._interval = interval
        self._running = False
        if ignore_exceptions:
            # If chosen not to ignore exceptions and coroutine takes more time to comp-
            # lete than the set interval, awaiting *get_result* will NOT result
            # in an *AttributeError*.
            #
            # NOTE: This will not make the *Periodic* handle exceptions thrown from the
            # coroutine gracefully, it serves the aforementioned purpose. For better
            # exception handling, massive design overhaul is needed. :D
            self._result: RType = object()  # type: ignore

    @property
    def name(self) -> str:
        return f"Periodic-{self._coro.__name__}"

    @property
    def interval(self) -> float:
        return self._interval

    @property
    def running(self) -> bool:
        return self._running

    def _start(self) -> None:
        self._main = self._loop.create_task(self._run(), name=f"{self.name}-main")

    def _stop(self) -> None:
        self._main.cancel()

    async def _inner(self, counter: int) -> None:
        self._task = self._loop.create_task(
            self._coro(*self._args, **self._kwargs), name=f"{self.name}-{counter}"
        )
        async with self._lock:
            self._result = await self._task

    async def _run(self) -> None:
        for c in itertools.count(1):
            # I don't like this assignment but it is needed for the interpreter to stop
            # complaining about the unhandled *asyncio.gather* exception. It is dealt
            # with in the second suppress - by calling *.result* on the *_gather_fut*
            # which results in *asyncio.CancelledError* exception :)
            _gather_fut: asyncio.Future = asyncio.gather(
                self._inner(c), asyncio.sleep(self.interval)
            )
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    _gather_fut, timeout=self.interval,
                )
            with suppress(asyncio.CancelledError):
                _gather_fut.result()

    def start(self, delay: float = None) -> None:
        if self.running:
            raise RuntimeError("Coroutine is already running!")
        self._running = True
        if delay is None:
            self._loop.call_soon(self._start)
        else:
            self._loop.call_later(delay, self._start)

    def stop(self, delay: float = None) -> None:
        if not self.running:
            raise RuntimeError("Coroutine is already stopped!")
        self._running = False
        if delay is None:
            self._stop()
        else:
            self._loop.call_later(delay, self._stop)

    async def get_result(self) -> RType:
        async with self._lock:
            return self._result
