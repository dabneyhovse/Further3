from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from gadt import GADT


class Duration(metaclass=GADT):
    Finite: Callable[[timedelta], Duration]
    Infinite: Duration
    NAN: Duration

    @staticmethod
    def from_timedelta(duration: timedelta) -> Duration:
        if abs(duration) == duration:
            return Duration.Finite(duration)
        else:
            return Duration.NAN

    @staticmethod
    def zero():
        return Duration.Finite(timedelta())

    def __add__(self, other: Duration) -> Duration:
        match self, other:
            case Duration.Finite(a), Duration.Finite(b):
                return Duration.Finite(a + b)
            case (Duration.Infinite, Duration.Finite(_)) | \
                 (Duration.Finite(_), Duration.Infinite) | \
                 (Duration.Infinite, Duration.Infinite):
                return Duration.Infinite
            case _:
                return Duration.NAN

    def __sub__(self, other: Duration) -> Duration:
        match self, other:
            case Duration.Finite(a), Duration.Finite(b):
                return Duration.Finite(a - b) if a >= b else Duration.NAN
            case Duration.Infinite, Duration.Finite(_):
                return Duration.Infinite
            case _:
                return Duration.NAN

    def __mul__(self, scale: float) -> Duration:
        match self:
            case Duration.Finite(a) if scale >= 0:
                return Duration.Finite(a * scale)
            case Duration.Infinite if scale >= 0:
                return Duration.Infinite
            case _:
                return Duration.NAN

    def __truediv__(self, scale: float) -> Duration:
        match self:
            case Duration.Finite(a) if scale > 0:
                return Duration.Finite(a / scale)
            case Duration.Infinite if scale > 0:
                return Duration.Infinite
            case _:
                return Duration.NAN

    def __str__(self) -> str:
        match self:
            case Duration.Finite(a):
                return str(a)
            case Duration.Infinite:
                return "∞"
            case Duration.NAN:
                return "NAN"
