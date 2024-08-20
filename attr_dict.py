from collections.abc import MutableMapping
from typing import Optional


class AttrDictView[K, V]:
    def __init__(self, init_dict: Optional[MutableMapping[K, V]] = None) -> None:
        if init_dict is None:
            self.wrapped = dict()
        else:
            self.wrapped = init_dict

        if "defaults" not in self:
            self["defaults"] = None

    def __getattr__(self, attr):
        if attr == "defaults":
            if self["defaults"] is None:
                self["defaults"] = dict()
            return AttrDictView(self["defaults"])
        elif attr in self.wrapped:
            return self[attr]
        elif self["defaults"] is not None:
            self[attr] = self["defaults"][attr]
            return self[attr]
        else:
            raise AttributeError(f"No such attribute or dictionary element: {attr}")

    def __setattr__(self, attr, value):
        if attr in ["wrapped"] or hasattr(super(), attr):
            super().__setattr__(attr, value)
        else:
            self[attr] = value

    def __getitem__(self, key: K) -> V:
        return super().__getattribute__("wrapped").__getitem__(key)

    def __setitem__(self, key: K, value: V) -> None:
        super().__getattribute__("wrapped").__setitem__(key, value)

    def __contains__(self, key: K) -> bool:
        return super().__getattribute__("wrapped").__contains__(key)
