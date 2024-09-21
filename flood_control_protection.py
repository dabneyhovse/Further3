import sys
import traceback
from asyncio import sleep
from collections.abc import Callable, Coroutine
from functools import wraps

from telegram.error import RetryAfter, TimedOut

from bot_communication import UpwardsCommunication, ConnectionListener
from decorator_tools import arg_decorator
from settings import Settings

next_recovery_id: int = 0


@arg_decorator
def protect_from_telegram_flood_control[** P, T](f: Callable[P, Coroutine[None, None, T]],
                                                 connection_listener: ConnectionListener) -> \
        Callable[P, Coroutine[None, None, T]]:
    @wraps(f)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        global next_recovery_id

        recovery_id: int = -1
        for i in range(Settings.max_telegram_flood_control_retries - 1):
            try:
                if recovery_id >= 0:
                    print(f"Automatically recovering...\n"
                          f"Recovery number: {recovery_id}\n", file=sys.stderr)
                return await f(*args, **kwargs)
            except RetryAfter as e:
                recovery_id = next_recovery_id
                print(f"Caught exception:\n"
                      f"...\n"
                      f"{e.message}\n"
                      f"Recovery id: {recovery_id}\n"
                      f"Retry number: {i + 1}\n"
                      f"Will automatically recover.\n", file=sys.stderr)
                next_recovery_id += 1
                await connection_listener.send(UpwardsCommunication.FloodControlIssues(e.retry_after))
                await sleep(e.retry_after + Settings.flood_control_buffer_time)
        return await f(*args, **kwargs)

    return wrapped


def protect_from_telegram_timeout[** P, T](f: Callable[P, Coroutine[None, None, T]]) -> \
        Callable[P, Coroutine[None, None, T]]:
    @wraps(f)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        global next_recovery_id

        recovery_id: int = -1
        for i in range(Settings.max_telegram_time_out_retries - 1):
            try:
                if recovery_id >= 0:
                    print(f"Automatically recovering...\n"
                          f"Recovery number: {recovery_id}\n", file=sys.stderr)
                return await f(*args, **kwargs)
            except TimedOut:
                recovery_id = next_recovery_id
                print(f"Caught exception:\n"
                      f"{traceback.format_exc()}\n"
                      f"Recovery id: {recovery_id}\n"
                      f"Retry number: {i + 1}\n"
                      f"Will automatically recover.\n", file=sys.stderr)
                next_recovery_id += 1
                await sleep(Settings.telegram_time_out_buffer_time)
        return await f(*args, **kwargs)

    return wrapped
