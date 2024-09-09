from __future__ import annotations

from asyncio import Lock, Event
from collections import deque
from collections.abc import AsyncIterator, Iterable, Iterator
from contextlib import asynccontextmanager


class AsyncQueue[T](Iterable[T]):
    _async_iterator: AsyncIterator[T]
    _iterator_lock: Lock
    _non_empty_event: Event
    _queue: deque[T]

    class AsyncIterator(AsyncIterator[T]):
        source: AsyncQueue[T]

        def __init__(self, source: AsyncQueue[T]):
            self.source = source

        async def __anext__(self) -> T:
            await self.source._non_empty_event.wait()
            print("Received non-empty event")
            return await self.source.pop()

    class DestructiveIterator(Iterator[T]):
        source: AsyncQueue[T]

        def __init__(self, source: AsyncQueue[T]):
            self.source = source

        def __next__(self) -> T:
            if self.source._queue:
                return self.source._queue.popleft()
            else:
                raise StopIteration

    def __init__(self):
        self._queue = deque()
        self._iterator_lock = Lock()
        self._async_iterator = AsyncQueue.AsyncIterator(self)
        self._destructive_iterator = AsyncQueue.DestructiveIterator(self)
        self._non_empty_event = Event()

    def __iter__(self):
        return iter(self._queue)

    @property
    def destructive_iter(self):
        return self._destructive_iterator

    @asynccontextmanager
    async def async_iter(self):
        await self._iterator_lock.acquire()
        yield self._async_iterator
        self._iterator_lock.release()

    def __getitem__(self, item) -> T:
        return self._queue[item]

    def __setitem__(self, key, value: T) -> None:
        self._queue[key] = value

    async def append(self, value: T) -> None:
        self._queue.append(value)
        self._non_empty_event.set()

    async def appendleft(self, value: T) -> None:
        self._queue.appendleft(value)
        self._non_empty_event.set()

    async def pop(self) -> T:
        out: T = self._queue.pop()
        if not self._queue:
            self._non_empty_event.clear()
        return out

    async def popleft(self) -> T:
        out: T = self._queue.popleft()
        if not self._queue:
            self._non_empty_event.clear()
        return out

    def __bool__(self) -> bool:
        return bool(self._queue)

    def __len__(self) -> int:
        return len(self._queue)

    def __repr__(self) -> str:
        return f"AsyncQueue([{','.join(map(repr, self._queue))}])"
