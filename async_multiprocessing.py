import asyncio
from collections.abc import Callable
from multiprocessing import Process
from typing import Optional

from util import Wrapper


def wrapped_out_target[T, ** P](_await_process_target: Callable[P, T], _await_process_out: Wrapper[T],
                                *_await_process_args: P.args, **_await_process_kwargs: P.kwargs) -> None:
    _await_process_out.put(_await_process_target(*_await_process_args, **_await_process_kwargs))


async def await_process[T, ** P](target: Callable[P, T], init_delay: float = 0.125, increment: float = 0.25,
                                 abort_signal: Wrapper[bool] | None = None,
                                 args: Optional[P.args] = None, kwargs: Optional[P.kwargs] = None) -> T:
    if args is None:
        args = ()
    if kwargs is None:
        kwargs = {}

    output: Wrapper[T] = Wrapper()
    process: Process = Process(target=wrapped_out_target, args=((target, output) + args), kwargs=kwargs, daemon=True)

    process.run()

    await asyncio.sleep(init_delay)

    while (abort_signal is None or abort_signal.get(default=False)) and process.is_alive():
        await asyncio.sleep(increment)

    if process.is_alive():
        process.kill()

    return output.get_or_err()
