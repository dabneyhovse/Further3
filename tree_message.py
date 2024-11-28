from __future__ import annotations

from typing import Callable

from gadt import GADT


class TreeMessage(metaclass=GADT):
    Text: Callable[[str], TreeMessage]
    InlineCode: Callable[[str], TreeMessage]
    Sequence: Callable[[list[TreeMessage]], TreeMessage]
    Named: Callable[[str, TreeMessage], TreeMessage]
    Skip: TreeMessage

    @property
    def sequence_nesting_depth(self) -> int:
        match self:
            case TreeMessage.Sequence(sequence):
                return 1 + max((sub.sequence_nesting_depth for sub in sequence), default=0)
            case _:
                return 0

    def __str__(self) -> str:
        indent = " " * 4

        match self:
            case TreeMessage.Skip:
                return ""
            case TreeMessage.Text(text):
                return text
            case TreeMessage.InlineCode(text):
                return f"<code>{text}</code>"
            case TreeMessage.Sequence(sequence):
                return (
                    ("\n" * self.sequence_nesting_depth).join(str(sub) for sub in sequence if sub != TreeMessage.Skip)
                )
            case TreeMessage.Named(key, TreeMessage.Sequence(_) as value):
                return f"<b>{key}:</b>\n{indent}{str(value).replace('\n', '\n' + indent)}"
            case TreeMessage.Named(key, value):
                return f"<b>{key}:</b> {value}"

    def __or__(self, other: TreeMessage) -> TreeMessage:
        match self:
            case TreeMessage.Skip:
                return other
            case _:
                return self

    def __and__(self, other: TreeMessage) -> TreeMessage:
        match self:
            case TreeMessage.Skip:
                return self
            case _:
                return other

    def __xor__(self, other: TreeMessage) -> TreeMessage:
        match self, other:
            case TreeMessage.Skip, TreeMessage.Skip:
                return TreeMessage.Skip
            case _, TreeMessage.Skip:
                return self
            case TreeMessage.Skip, _:
                return other

    def __matmul__(self, condition: object) -> TreeMessage:
        return self if bool(condition) else TreeMessage.Skip
