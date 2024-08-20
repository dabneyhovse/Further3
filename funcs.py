from collections.abc import Callable

def compose[** P, T, U](f: Callable[[T], U], g: Callable[P, T]) -> Callable[P, U]:
    def composed(*args: P.args, **kwargs: P.kwargs) -> U:
        return f(g(*args, **kwargs))

    return composed
