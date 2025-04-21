import inspect
import json
import os
import pickle
from collections.abc import Buffer
from enum import Enum
from typing import Any, get_type_hints, get_origin, get_args, Union
from inspect import getmodule

def deep_type_check(value: Any, expected_type: Any) -> bool:
    if expected_type is Any:
        return True
    origin = get_origin(expected_type)
    args = get_args(expected_type)
    if origin is Union:
        return any(deep_type_check(value, t) for t in args)
    if origin in {list, tuple, set}:
        return isinstance(value, origin) and all(deep_type_check(v, args[0]) for v in value)
    if origin is dict:
        return isinstance(value, dict) and all(
            deep_type_check(k, args[0]) and deep_type_check(v, args[1]) for k, v in value.items()
       )
    return isinstance(value, expected_type)


class PersistenceSource(Enum):
    JSON = "json"
    PICKLE = "pickle"

    def __init__(self, persistence_type: str):
        match persistence_type:
            case "json":
                self.source = json
                self.format_modifier = ""
            case "pickle":
                self.source = pickle
                self.format_modifier = "b"

    def dump(self, path: os.PathLike, obj: Any):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w" + self.format_modifier) as f:
            self.source.dump(obj, f, indent=2)

    def dumps(self, obj: Any) -> str | bytes:
        return self.source.dumps(obj, indent=2)

    def load(self, path: os.PathLike):
        with open(path, "r" + self.format_modifier) as f:
            return self.source.load(f)

    def loads(self, data: Buffer) -> Any:
        return self.source.loads(data)


def _persistent_new_and_init(_self, *_args, **_kwargs):
    raise TypeError("Can't instantiate a persistent singleton")


def persistent_singleton(persistence_source: PersistenceSource, persistence_file: os.PathLike,
                         hot_reload: bool = False):
    def wrapper(cls):
        original_annotations = get_type_hints(cls, globalns=vars(getmodule(cls)))
        namespace = dict(cls.__dict__)
        namespace["__annotations__"] = original_annotations
        persistent_namespace = dict(PersistentSingleton.__dict__)
        persistent_namespace.pop("__annotations__", None)
        namespace.update(persistent_namespace)

        if len(cls.__bases__) != 1 or cls.__bases__[0] != object:
            raise NotImplementedError("Can't create a persistent singleton subtype yet")

        bases = (PersistentSingletonInstance,)

        singleton = PersistentSingleton(cls.__name__, bases=bases, namespace=namespace)
        singleton.__persistence_source__ = persistence_source
        singleton.__persistence_file_path__ = persistence_file
        singleton.__hot_reload__ = hot_reload
        if os.path.isfile(singleton.__persistence_file_path__):
            singleton.reload()
        singleton.push()
        return singleton

    return wrapper


class PersistentSingleton(type):
    __persistence_source__: PersistenceSource
    __persistence_file_path__: os.PathLike
    __hot_reload__: bool = False

    def __new__(mcs, name, bases, namespace):
        return super().__new__(mcs, name, bases, namespace)

    def __init__(cls, name, bases, namespace):
        super().__init__(name, bases, namespace)

        cls_annotations = inspect.get_annotations(cls)
        cls.__singleton_fields__ = list()
        cls.__persistence_dict__ = dict()
        for field_name, _field_type in cls_annotations.items():
            cls.__singleton_fields__.append(field_name)
            if hasattr(cls, field_name):
                cls.__persistence_dict__[field_name] = getattr(cls, field_name)
                delattr(cls, field_name)
        if hasattr(cls, "__init__"):
            cls.__dataclass_init__ = cls.__init__
        cls.__new__ = _persistent_new_and_init
        cls.__init__ = _persistent_new_and_init

    def __getattribute__(cls, attr):
        if attr not in ["__getattribute__", "__getattr__", "__singleton_fields__", "__setattr__"] and \
                hasattr(cls, "__singleton_fields__") and \
                attr in cls.__singleton_fields__:
            if cls.__hot_reload__:
                cls.reload()
            if attr in cls.__persistence_dict__:
                return cls.__persistence_dict__[attr]
        return super().__getattribute__(attr)

    def __setattr__(cls, attr, value):
        if hasattr(cls, "__singleton_fields__") and attr in cls.__singleton_fields__:
            expected_type = get_type_hints(cls).get(attr)
            if expected_type is not None and not deep_type_check(value, expected_type):
                if type(expected_type) == type:
                    value = expected_type(value)
                else:
                    raise TypeError(f"Expected type '{expected_type}' for attribute '{attr}', but got '{type(value)}'")
            cls.__persistence_dict__[attr] = value
            cls.push()
        else:
            super().__setattr__(attr, value)


class PersistentSingletonInstance(metaclass=PersistentSingleton):
    @classmethod
    def push(cls):
        cls.__persistence_source__.dump(cls.__persistence_file_path__, cls.__persistence_dict__)

    @classmethod
    def reload(cls):
        loaded: dict[str, Any] = cls.__persistence_source__.load(cls.__persistence_file_path__)
        for key, value in loaded.items():
            if key in cls.__singleton_fields__:
                setattr(cls, key, value)
