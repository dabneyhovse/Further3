from __future__ import annotations

from asyncio import Lock, Event
from collections import deque
from collections.abc import AsyncIterator, Iterable, Iterator
from contextlib import asynccontextmanager

from gadt.standard.__init__ import Maybe


class AsyncQueue[T](Iterable[T]):
    _async_iterator: AsyncIterator[T]
    _iterator_lock: Lock
    _non_empty_event: Event
    _queue: deque[Maybe[T]]

    class AsyncIterator(AsyncIterator[T]):
        source: AsyncQueue[T]

        def __init__(self, source: AsyncQueue[T]):
            self.source = source

        async def __anext__(self) -> T:
            while not self.source:
                await self.source._non_empty_event.wait()
            match (await self.source.maybe_popleft()):
                case Maybe.Just(x):
                    return x
                case Maybe.Nothing:
                    raise StopAsyncIteration

    class DestructiveIterator(Iterator[T]):
        source: AsyncQueue[T]

        def __init__(self, source: AsyncQueue[T], reverse: bool = False):
            self.source = source
            self.reverse = reverse

        def __next__(self) -> T:
            if self.source._queue:
                out: T = self.source._queue.pop() if self.reverse else self.source._queue.popleft()
                if not self.source._queue:
                    self.source._non_empty_event.clear()
                match out:
                    case Maybe.Just(x):
                        return x
                    case Maybe.Nothing:
                        raise StopIteration
            else:
                raise StopIteration

    def __init__(self):
        self._queue = deque()
        self._iterator_lock = Lock()
        self.read_lock = Lock()
        self._async_iterator = AsyncQueue.AsyncIterator(self)
        self._destructive_iterator = AsyncQueue.DestructiveIterator(self)
        self._reverse_destructive_iterator = AsyncQueue.DestructiveIterator(self, reverse=True)
        self._non_empty_event = Event()

    def __iter__(self):
        return (x.unwrap() for x in self._queue if x.is_just())

    @property
    def destructive_iter(self):
        return self._destructive_iterator

    @property
    def reverse_destructive_iter(self):
        return self._reverse_destructive_iterator

    @asynccontextmanager
    async def async_iter(self):
        await self._iterator_lock.acquire()
        yield self._async_iterator
        self._iterator_lock.release()

    def __getitem__(self, item) -> T:
        match self._queue[item]:
            case Maybe.Just(x):
                return x
            case Maybe.Nothing:
                raise IndexError("Stop iteration element")

    def __setitem__(self, key, value: T) -> None:
        self._queue[key] = Maybe.Just(value)

    async def append(self, value: T) -> None:
        self._queue.append(Maybe.Just(value))
        self._non_empty_event.set()

    async def appendleft(self, value: T) -> None:
        self._queue.appendleft(Maybe.Just(value))
        self._non_empty_event.set()

    async def append_stop_iteration(self):
        self._queue.append(Maybe.Nothing)
        self._non_empty_event.set()

    async def appendleft_stop_iteration(self):
        self._queue.appendleft(Maybe.Nothing)
        self._non_empty_event.set()

    async def pop(self) -> T:
        async with self.read_lock:
            out: Maybe[T] = self._queue.pop()
            if not self._queue:
                self._non_empty_event.clear()
            match out:
                case Maybe.Just(value):
                    return value
                case Maybe.Nothing:
                    raise IndexError("Stop iteration element")

    async def popleft(self) -> T:
        async with self.read_lock:
            out: Maybe[T] = self._queue.popleft()
            if not self._queue:
                self._non_empty_event.clear()
            match out:
                case Maybe.Just(value):
                    return value
                case Maybe.Nothing:
                    raise IndexError("Close queue element")

    async def maybe_pop(self) -> Maybe[T]:
        async with self.read_lock:
            out: Maybe[T] = self._queue.popleft()
            if not self._queue:
                self._non_empty_event.clear()
            return out

    async def maybe_popleft(self) -> Maybe[T]:
        async with self.read_lock:
            out: Maybe[T] = self._queue.popleft()
            if not self._queue:
                self._non_empty_event.clear()
            return out

    def __bool__(self) -> bool:
        return bool(self._queue) and bool(self._queue[0])

    def __len__(self) -> int:
        return len(self._queue) if Maybe.Nothing not in self._queue else self._queue.index(Maybe.Nothing)

    def __repr__(self) -> str:
        return f"AsyncQueue([{','.join(map(repr, self._queue))}])"
