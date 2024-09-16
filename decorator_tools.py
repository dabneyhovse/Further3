from collections.abc import Callable
from typing import Concatenate


def arg_decorator[** P, ** Q, T, U](func: Callable[Concatenate[Callable[Q, U], P], T]) -> \
        Callable[P, Callable[[Callable[Q, U]], T]]:
    def decorator_wrapper(*args: P.args, **kwargs: P.kwargs) -> Callable[[Callable[Q, U]], T]:
        def decorator(wrapped: Callable[Q, U]) -> T:
            return func(wrapped, *args, **kwargs)

        return decorator

    return decorator_wrapper


# TODO make a type-safe version of property (property would retain type information and would be thus parametrized by
# the self type and the property type
def method_decorator[S, T, U, ** P](dec: Callable[[Callable[P, T]], U]) -> \
        Callable[[Callable[Concatenate[S, P], T]], property]:
    def safe_decorator(method: Callable[Concatenate[S, P], T]) -> property:
        def property_callback(self: S) -> U:
            def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
                return method(self, *args, **kwargs)

            return dec(wrapped)

        return property(property_callback)

    return safe_decorator


# map_arg_decorator(m)(f) produces a function that applies the map, m, over the first argument to f
@arg_decorator
def map_first_arg_decorator[S, T, U, ** P](f: Callable[Concatenate[T, P], U], m: Callable[[S], T]) -> \
        Callable[Concatenate[S, P], U]:
    def decorator(x: S, *args: P.args, **kwargs: P.kwargs) -> U:
        return f(m(x), *args, **kwargs)

    return decorator


# map_arg_decorator(m)(f) produces a function that applies the map, m, over the first argument to f using the rest of
# the args passed to f
@arg_decorator
def map_all_to_first_arg_decorator[S, T, U, ** P](f: Callable[Concatenate[T, P], U],
                                                  m: Callable[Concatenate[S, P], T]) -> \
        Callable[Concatenate[S, P], U]:
    def decorator(x: S, *args: P.args, **kwargs: P.kwargs) -> U:
        return f(m(x, *args, **kwargs), *args, **kwargs)

    return decorator


# map_arg_decorator(m)(f) produces a function that applies the map, m, over every argument to f
@arg_decorator
def map_all_args_decorator[T, U, ** P](f: Callable[[T], U], m: Callable[P, T]) -> Callable[P, U]:
    def decorator(*args: P.args, **kwargs: P.kwargs) -> U:
        return f(m(*args, **kwargs))

    return decorator
