from __future__ import annotations

from asyncio import to_thread
from collections.abc import Callable, Coroutine
from multiprocessing.connection import Connection

from gadt import GADT


class UpwardsCommunication(metaclass=GADT):
    CleanShutdown: UpwardsCommunication
    ExceptionShutdown: Callable[[Exception], UpwardsCommunication]
    FloodControlIssues: UpwardsCommunication


class DownwardsCommunication(metaclass=GADT):
    ShutDown: Callable[[int], DownwardsCommunication]


class ConnectionListener[T]:
    connection: Connection

    def __init__(self, connection: Connection):
        self.connection = connection

    async def listen(self, handler: Callable[[T], Coroutine[None, None, None]]):
        while True:
            communication: T = await to_thread(self.connection.recv)
            await handler(communication)

    async def send(self, communication: UpwardsCommunication):
        self.connection.send(communication)
