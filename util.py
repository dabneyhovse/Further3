import sys
from collections import deque
from collections.abc import Callable, Iterable, Generator, Collection, Sequence
from enum import Enum
from itertools import islice, chain, repeat
from numbers import Number
from typing import Optional, Any

from attr_dict import AttrDictView
from funcs import compose

simple_table_chars = AttrDictView({
    "s": "*",
    "v": "|",
    "h": "-",
    "tl": "+",
    "tr": "+",
    "bl": "+",
    "br": "+",
    "l": "+",
    "t": "+",
    "r": "+",
    "b": "+",
    "c": "+"
})

rounded_table_chars = AttrDictView({
    "s": "*",
    "v": "│",
    "h": "–",
    "tl": "╭",
    "tr": "╮",
    "bl": "╰",
    "br": "╯",
    "l": "├",
    "t": "┬",
    "r": "┤",
    "b": "┴",
    "c": "┼"
})


def bold_unicode_char(c: int) -> int:
    if ord('a') <= c <= ord('z'):
        return c - ord('a') + 0x0001D5EE
    elif ord('A') <= c <= ord('Z'):
        return c - ord('A') + 0x0001D5D4
    else:
        return c


def bold_unicode(text: str) -> str:
    return "".join(map(compose(chr, compose(bold_unicode_char, ord)), text))


def draw_table(rows: list[list[str]], chars=rounded_table_chars, header_format=Optional[Callable[[str], str]]) -> str:
    cols = list(zip(*rows))
    if header_format is not None:
        formatted_cols = [map(header_format, cols[0])] + cols[1:]
        formatted_rows = list(zip(*formatted_cols))
    else:
        formatted_rows = rows
    out = ""
    col_widths = [max(len(cell) + 2 if cell else 0 for cell in col) for col in cols]
    out += chars.tl
    for col_num, width in enumerate(col_widths):
        if col_num:
            out += chars.t
        out += chars.h * width
    out += chars.tr
    for row_num, (row, formatted_row) in enumerate(zip(rows, formatted_rows)):
        if row_num:
            out += chars.l
            for col_num, width in enumerate(col_widths):
                if col_num:
                    out += chars.c
                out += chars.h * width
            out += chars.r
        out += "\n"
        for cell, formatted_cell, width in zip(row, formatted_row, col_widths):
            out += chars.v
            if cell:
                out += chars.s + formatted_cell + chars.s * (width - len(cell) - 1)
        out += chars.v + "\n"
    out += chars.bl
    for col_num, width in enumerate(col_widths):
        if col_num:
            out += chars.b
        out += chars.h * width
    out += chars.br

    return out


def count_iterable(i: Iterable[Any]) -> int:
    return sum(1 for _ in i)


class Wrapper[T]:
    class Uninitialized(Enum):
        UNINITIALIZED = 0

    class UninitializedError(Exception):
        pass

    def __init__(self, value: T | Uninitialized = Uninitialized.UNINITIALIZED) -> None:
        self.value: T | Wrapper.Uninitialized = value

    def put(self, value: T | Uninitialized) -> None:
        self.value = value

    def get[U](self, default: U = Uninitialized) -> T | U:
        if type(self.value) is Wrapper.Uninitialized:
            return default
        else:
            return self.value

    def get_or_err(self) -> T:
        if type(self.value) is Wrapper.Uninitialized:
            raise Wrapper.UninitializedError(self.value)
        else:
            return self.value


def sliding_window[T, X](it: Iterable[T], n: int, extend_left: bool = False, extend_right: bool = False,
                         out_of_bounds: X = None) -> Generator[tuple[T | X, ...], None, None]:
    augmented_it: Iterable[T | X] = chain(
        repeat(out_of_bounds, n - 1) if extend_left else [],
        it,
        repeat(out_of_bounds, n - 1) if extend_right else []
    )
    window: deque[T | X] = deque(islice(augmented_it, n), maxlen=n)
    for elem in augmented_it:
        yield tuple(window)
        window.append(elem)
    yield tuple(window)


def escape_str(raw: str, seqs: Iterable[str], escape: str = "\\") -> str:
    out: str = raw.replace(escape, escape + escape)
    for seq in seqs:
        out = out.replace(seq, escape + seq)
    return out


def trim_docstring(docstring) -> str:
    """Largely lifted off the PEP 257 description because I'm too lazy to write it myself"""
    if not docstring:
        return ""
    # Convert tabs to spaces (following the normal Python rules)
    # and split into a list of lines:
    lines = docstring.expandtabs().splitlines()
    # Determine minimum indentation (first line doesn't count):
    indent = sys.maxsize
    for line in lines[1:]:
        stripped = line.lstrip()
        if stripped:
            indent = min(indent, len(line) - len(stripped))
    # Remove indentation (first line is special):
    trimmed = [lines[0].strip()]
    if indent < sys.maxsize:
        for line in lines[1:]:
            trimmed.append(line[indent:].rstrip())
    # Strip off trailing and leading blank lines:
    while trimmed and not trimmed[-1]:
        trimmed.pop()
    while trimmed and not trimmed[0]:
        trimmed.pop(0)
    # Return a single string:
    return "\n".join(trimmed).rstrip()


def interpolate_index(seq: Sequence[float], x: float) -> float:
    i: int = int(x)
    if x == i:
        return seq[i]
    else:
        return seq[i] * (i - x + 1) + seq[i + 1] * (x - i)
