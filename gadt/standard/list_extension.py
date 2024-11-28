from gadt.standard import Maybe


def filter_just[T](xs: list[Maybe[T]]) -> list[T]:
    return [x.unwrap() for x in xs]
