from __future__ import annotations

from collections.abc import Callable

from gadt import GADT


class Maybe[T](metaclass=GADT):
    Nothing: Maybe[T]
    Some: Callable[[T], Maybe[T]]


if __name__ == "__main__":
    print(type(Maybe.Nothing))
    print(type(Maybe.Some(3))(4))
