from __future__ import annotations

from collections.abc import Hashable, Mapping, MutableMapping, Iterable, Collection, ItemsView, Iterator, KeysView, \
    ValuesView
from typing import Self


class DoubleDict[K: Hashable, V: Hashable](MutableMapping[K, V]):
    def __init__(self, source: Mapping[K, V] | Collection[tuple[K, V]] | ItemsView[K, V] | None = None) -> None:
        match source:
            case None:
                self._forward: dict[K, V] = dict()
                self._reverse: dict[V, K] = dict()
            case Mapping():
                self._forward: dict[K, V] = dict(source)
                self._reverse: dict[V, K] = dict(((v, k) for k, v in source.items()))
            case Collection() | ItemsView():
                self._forward: dict[K, V] = dict(source)
                self._reverse: dict[V, K] = dict(((v, k) for k, v in source))

    @classmethod
    def _direct_init(cls, forward: dict[K, V], reverse: dict[V, K]) -> Self:
        out: DoubleDict[K, V] = cls()
        out._forward = forward
        out._reverse = reverse
        return out

    def __setitem__(self, k: K, v: V) -> None:
        assert k not in self._forward or self._forward.__getitem__(k).__hash__() == v.__hash__()
        assert v not in self._reverse or self._reverse.__getitem__(v).__hash__() == k.__hash__()

        self._forward.__setitem__(k, v)
        self._reverse.__setitem__(v, k)

    def __delitem__(self, k: K) -> None:
        v: V = self._forward.pop(k)
        self._reverse.__delitem__(v)

    def __getitem__(self, k: K) -> V:
        return self._forward.__getitem__(k)

    def __len__(self) -> int:
        return len(self._forward)

    def __iter__(self) -> Iterator[K]:
        return iter(self._forward)

    def __contains__(self, k: K) -> bool:
        return self._forward.__contains__(k)

    def items(self) -> ItemsView[K, V]:
        return self._forward.items()

    def keys(self) -> KeysView[K]:
        return self._forward.keys()

    def values(self) -> ValuesView[V]:
        return self._forward.values()

    def get[X](self, k: K, default: X = None) -> V | X:
        return self._forward.get(k, default)

    def pop[X](self, k: K, default: X = None) -> V | X:
        out: V = self._forward.pop(k, default)
        if out in self._reverse:
            self._reverse.__delitem__(out)
        return self._reverse.__getitem__(out)

    @property
    def reverse(self) -> DoubleDict[V, K]:
        return self._direct_init(self._reverse, self._forward)
