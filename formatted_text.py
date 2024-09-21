from __future__ import annotations

from abc import ABCMeta
from collections.abc import Generator, Iterable, Iterator, Reversible
from enum import IntFlag, EnumMeta
from typing import SupportsIndex, Self

from double_dict import DoubleDict
from util import sliding_window


class AbstractEnumMeta(EnumMeta, ABCMeta):
    pass


class Format(Reversible[str], Iterable[str], IntFlag, metaclass=AbstractEnumMeta):
    NONE = 0
    BOLD = 1
    ITALIC = 2
    CODE = 4
    STRIKE = 8
    UNDERLINE = 16
    PRE = 32

    def __iter__(self) -> Iterator[str]:
        return iter(tag_names.reverse[1 << i] for i in range(6) if self & (1 << i))

    def __reversed__(self) -> Iterator[str]:
        return iter(tag_names.reverse[1 << i] for i in range(5, -1, -1) if self & (1 << i))


tag_names: DoubleDict[str, Format] = DoubleDict({
    "b": Format.BOLD,
    "i": Format.ITALIC,
    "code": Format.CODE,
    "s": Format.STRIKE,
    "u": Format.UNDERLINE,
    "pre": Format.PRE
})


class FormattedText(list[tuple[str, Format]]):
    def __init__(self, source: str | list) -> None:
        match source:
            case str():
                super().__init__()

                plain_chars: list[str] = []

                current_format: Format = Format.NONE
                chars: Generator[tuple[str | None, ...], None, None] = sliding_window(source, 7, extend_right=True)
                for window in chars:
                    for tag_name, tag_format in tag_names.items():
                        open_tag: str = f"<{tag_name}>"
                        if window[:len(open_tag)] == tuple(open_tag):
                            current_format |= tag_format
                            for _ in range(len(open_tag) - 1):
                                next(chars)
                            break

                        close_tag: str = f"</{tag_name}>"
                        if window[:len(close_tag)] == tuple(close_tag):
                            current_format &= ~tag_format
                            for _ in range(len(close_tag) - 1):
                                next(chars)
                            break
                    else:
                        self.append((window[0], current_format))
                        plain_chars.append(window[0])

                self.plain_text: str = "".join(plain_chars)
            case list():
                super().__init__(source)
                self.plain_text: str = "".join(next(zip(*self)))
            case _:
                raise TypeError("FormattedText must receive a list[tuple[str, Format]] or a str")

    def __str__(self) -> str:
        out: list[str] = []
        current_format: Format = Format.NONE
        for c, new_format in self:
            for opened in new_format & ~current_format:
                out.append(f"<{opened}>")
            for closed in reversed(~new_format & current_format):
                out.append(f"</{closed}>")
            out.append(c)
            current_format = new_format
        for closed in reversed(current_format):
            out.append(f"</{closed}>")
        return "".join(out)

    def __contains__(self, item: str | tuple[str, Format]) -> bool:
        match item:
            case str():
                return self.plain_text.__contains__(item)
            case _:
                return super().__contains__(item)

    def __getitem__(self, item: SupportsIndex) -> tuple[str, Format] | Self:
        out: tuple[str, Format] | list[tuple[str, Format]] = super().__getitem__(item)
        match out:
            case list():
                return FormattedText(out)
            case _:
                return out

    def find(self, item: str) -> int:
        return self.plain_text.find(item)

    def rfind(self, item: str) -> int:
        return self.plain_text.rfind(item)

    def __add__(self, other: Self) -> Self:
        return FormattedText(super().__add__(other))

    def break_message_text(self) -> FormattedText:
        max_len: int = 4096
        if len(self) > max_len:
            return self[:max_len - 3] + FormattedText("...")
        else:
            return self
