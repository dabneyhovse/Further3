from __future__ import annotations

from collections.abc import Callable as Callable
from typing import TypeVar

from gadt import GADT


class Something[T]:
    pass


class Maybe[T](metaclass=GADT):
    Nothing: Maybe[T]
    Just: Callable[[T], Maybe[T]]

    def __repr__(self):
        match self:
            case self.Nothing:
                return "Nothing"
            case self.Just(x):
                return f"Just({repr(x)})"


class Bool(metaclass=GADT):
    TrueBool: Bool
    FalseBool: Bool


class Product[T, U](metaclass=GADT):
    Pair: Callable[[T, U], Product[T, U]]


class IntTree(metaclass=GADT):
    Branch: Callable[[list[IntTree]], IntTree]
    Leaf: Callable[[int], IntTree]


class Impossible(metaclass=GADT):
    pass


class Expression[T](metaclass=GADT):
    Int: Callable[[int], Expression[int]]
    Bool: Callable[[bool], Expression[bool]]
    Plus: Callable[[Expression[int], Expression[int]], Expression[int]]
    Minus: Callable[[Expression[int], Expression[int]], Expression[int]]
    Not: Callable[[Expression[bool]], Expression[bool]]
    And: Callable[[Expression[bool], Expression[bool]], Expression[bool]]
    Or: Callable[[Expression[bool], Expression[bool]], Expression[bool]]
    Equal: Callable[[Expression[int], Expression[int]], Expression[bool]]
    IfElse: Callable[[Expression[bool], Expression[T], Expression[T]], Expression[T]]
    Nil: Expression[list[T]]
    Cons: Callable[[Expression[T], Expression[list[T]]], Expression[list[T]]]

    def __str__(self):
        match self:
            case Expression.Int(x):
                return str(x)
            case Expression.Bool(x):
                return str(x)
            case Expression.Plus(x, y):
                return f"({x} + {y})"
            case Expression.Minus(x, y):
                return f"({x} - {y})"
            case Expression.Not(x):
                return f"(!{x})"
            case Expression.And(x, y):
                return f"({x} & {y})"
            case Expression.Or(x, y):
                return f"({x} | {y})"
            case Expression.Equal(x, y):
                return f"({x} == {y})"
            case Expression.IfElse(p, x, y):
                return f"(if {p} then {x} else {y})"
            case Expression.Nil:
                return "[]"
            case Expression.Cons(x, y):
                return f"({x} :: {y})"

    def eval(self):
        match self:
            case Expression.Int(x):
                return x
            case Expression.Bool(x):
                return x
            case Expression.Plus(x, y):
                return x.eval() + y.eval()
            case Expression.Minus(x, y):
                return x.eval() - y.eval()
            case Expression.Not(x):
                return not x.eval()
            case Expression.And(x, y):
                return x.eval() and y.eval()
            case Expression.Or(x, y):
                return x.eval() or y.eval()
            case Expression.Equal(x, y):
                return x.eval() == y.eval()
            case Expression.IfElse(p, x, y):
                return x.eval() if p.eval() else y.eval()
            case Expression.Nil:
                return []
            case Expression.Cons(x, y):
                return [x.eval()] + y.eval()


if __name__ == "__main__":
    expr = Expression.Cons(
        Expression.IfElse(
            Expression.Or(
                Expression.Equal(
                    Expression.Int(3),
                    Expression.Plus(
                        Expression.Int(1),
                        Expression.Int(2),
                    )
                ),
                Expression.Not(
                    Expression.Equal(
                        Expression.Int(3),
                        Expression.Plus(
                            Expression.Int(4),
                            Expression.Int(5),
                        )
                    )
                )
            ),
            Expression.Int(3),
            Expression.Minus(
                Expression.Int(9),
                Expression.Int(5)
            )
        ),
        Expression.Cons(
            Expression.Int(4),
            Expression.Nil
        )
    )
    print(expr)
    print(expr.eval())