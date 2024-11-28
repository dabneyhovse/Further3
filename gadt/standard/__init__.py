from __future__ import annotations

from collections.abc import Callable

from gadt import GADT


class Maybe[T](metaclass=GADT):
    Nothing: Maybe[T]
    Just: Callable[[T], Maybe[T]]

    def map[U](self, f: Callable[[T], U]) -> Maybe[U]:
        match self:
            case Maybe.Nothing:
                return Maybe.Nothing
            case Maybe.Just(x):
                return Maybe.Just(f(x))

    def apply[U](self, g: Maybe[Callable[[T], U]]) -> Maybe[U]:
        match self, g:
            case Maybe.Nothing, _:
                return Maybe.Nothing
            case _, Maybe.Nothing:
                return Maybe.Nothing
            case Maybe.Just(f), Maybe.Just(x):
                return Maybe.Just(f(x))

    def bind[U](self, f: Callable[[T], Maybe[U]]) -> Maybe[U]:
        match self:
            case Maybe.Nothing:
                return Maybe.Nothing
            case Maybe.Just(x):
                return f(x)

    def apply_bind[U](self, g: Maybe[Callable[[T], Maybe[U]]]) -> Maybe[U]:
        match self, g:
            case Maybe.Nothing, _:
                return Maybe.Nothing
            case _, Maybe.Nothing:
                return Maybe.Nothing
            case Maybe.Just(f), Maybe.Just(x):
                return f(x)

    def is_just(self) -> bool:
        match self:
            case Maybe.Nothing:
                return False
            case _:
                return True

    def unwrap(self) -> T:
        match self:
            case Maybe.Nothing:
                raise ValueError("Cannot unwrap Maybe.Nothing")
            case Maybe.Just(x):
                return x

    def __bool__(self) -> bool:
        match self:
            case Maybe.Just(_):
                return True
            case Maybe.Nothing:
                return False


class Either[L, R](metaclass=GADT):
    Left: Callable[[L], Either[L, R]]
    Right: Callable[[R], Either[L, R]]

    def flip(self):
        match self:
            case Either.Left(x):
                return Either.Right(x)
            case Either.Right(x):
                return Either.Left(x)

    def map[U](self, f: Callable[[R], U]) -> Either[L, U]:
        match self:
            case Either.Left(_):
                return self
            case Either.Right(x):
                return Either.Right(f(x))

    def map_left[U](self, f: Callable[[L], U]) -> Either[U, R]:
        match self:
            case Either.Right(_):
                return self
            case Either.Left(x):
                return Either.Left(f(x))

    def apply[U](self, g: Either[L, Callable[[R], U]]) -> Either[L, U]:
        match self, g:
            case Either.Left(_), _:
                return self
            case _, Either.Left(_):
                return g
            case Either.Right(f), Either.Right(x):
                return Either.Right(f(x))

    def bind[U](self, f: Callable[[R], Either[L, U]]) -> Either[L, U]:
        match self:
            case Either.Left(_):
                return self
            case Either.Right(x):
                return f(x)

    def apply_bind[U](self, g: Either[L, Callable[[R], Either[L, U]]]) -> Either[L, U]:
        match self, g:
            case Either.Left(_), _:
                return self
            case _, Either.Left(_):
                return g
            case Either.Right(f), Either.Right(x):
                return f(x)


class Both[L, R](metaclass=GADT):
    Pair: Callable[[L, R], Both[L, R]]

    def flip(self):
        match self:
            case Both.Pair(x, y):
                return Both.Pair(y, x)

    def map[U](self, f: Callable[[R], U]) -> Both[L, U]:
        match self:
            case Both.Pair(x, y):
                return Both.Pair(x, f(y))

    def map_left[U](self, f: Callable[[L], U]) -> Both[U, R]:
        match self:
            case Both.Pair(x, y):
                return Both.Pair(f(x), y)


class LinkedList[T](metaclass=GADT):
    Cons: Callable[[T, LinkedList[T]], LinkedList[T]]
    Nil: LinkedList[T]


class DAG[T](metaclass=GADT):
    Node: Callable[[*tuple[T, ...]], DAG[T]]
