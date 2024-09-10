from __future__ import annotations

import inspect
from collections.abc import Callable as CollectionsABCCallable
from collections.abc import _CallableGenericAlias as CollectionsABCCallableGenericAlias  # noqa
from types import GenericAlias as TypesGenericAlias
from typing import Callable as TypingCallable, Any, Self, get_args, TypeVar

type _CompoundConstrType = TypesGenericAlias | CollectionsABCCallableGenericAlias
type ConstrType = GADT | _CompoundConstrType


def _gadt_init(self, *_args, **_kwargs):
    raise TypeError("Can't instantiate a GADT using __init__")


def _gadt_repr(self):
    return self._constr_name_ + (
        ("(" + ", ".join(repr(datum) for datum in self._construction_data_) + ")")
        if self._construction_data_ is not None else ""
    )


type Constructor = GADT | CompoundConstructor


class GADT(type):
    @staticmethod
    def update_namespace(namespace):
        updated_namespace = {
            "__repr__": _gadt_repr
        }  # Defaults
        updated_namespace.update(namespace)
        updated_namespace.update({
            "__init__": _gadt_init
        })  # Overrides
        new_annotations = {
            "_constr_name_": str,
            "_constr_": Constructor,
            "_construction_data_": list[Any] | None,
            "_constr_type_": ConstrType
        }
        if "__annotations__" in updated_namespace:
            updated_namespace["__annotations__"].update(new_annotations)
        else:
            updated_namespace["__annotations__"] = new_annotations
        return updated_namespace

    def __new__(mcs, name, bases, namespace):
        updated_namespace = GADT.update_namespace(namespace)
        return super().__new__(mcs, name, bases, updated_namespace)

    def __init__(cls, name, bases, namespace):
        updated_namespace = GADT.update_namespace(namespace)
        super().__init__(name, bases, updated_namespace)

        cls_annotation_locals = {
            cls.__name__: cls
        }
        cls_annotations = inspect.get_annotations(cls, eval_str=True, locals=cls_annotation_locals)
        cls.__constructors__ = {}
        for constr_name, constr_type in cls_annotations.items():
            if constr_name[0] != "_":
                type_params: tuple[TypeVar, ...] = cls.__type_params__
                type_params_str: str = str(list(type_params)) if type_params else ""
                type_params_elided_str: str = f"[{', '.join(['...'] * len(type_params))}]" if type_params else ""
                type_error: TypeError = TypeError(
                    f"Constructors of the GADT {cls.__name__}{type_params_str} must either be "
                    f"of type {cls.__name__}{type_params_elided_str} or "
                    f"of type collections.abc.Callable[..., {cls.__name__}{type_params_elided_str}]. "
                    f"The type of {constr_name} cannot be {constr_type}."
                )

                origin = constr_type.__origin__ if hasattr(constr_type, "__origin__") else constr_type

                if not isinstance(origin, type):
                    raise type_error

                if issubclass(origin, cls):
                    obj: cls = object.__new__(cls)  # noqa
                    setattr(obj, "_constr_name_", constr_name)
                    setattr(obj, "_constr_", obj)
                    setattr(obj, "_construction_data_", None)
                    setattr(obj, "_constr_type_", constr_type)
                    setattr(cls, constr_name, obj)
                elif issubclass(origin, (CollectionsABCCallable, TypingCallable)):
                    match constr_type.__reduce__():
                        case (_, (_, (_, result_type))):
                            result_origin = (
                                result_type.__origin__ if hasattr(result_type, "__origin__") else result_type)

                            if not issubclass(result_origin, cls):
                                raise type_error

                            obj: CompoundConstructor = CompoundConstructor(cls, constr_name, constr_type)
                            setattr(cls, constr_name, obj)
                        case _:
                            raise TypeError(f"Unexpected structure of ({constr_type}).__reduce__().")
                else:
                    raise type_error


class CompoundConstructor(GADT):
    @staticmethod
    def _generate_type_init_args(gadt_cls: GADT, constr_name: str, constr_type: _CompoundConstrType) -> \
            tuple[str, tuple[type, ...], dict[str, Any]]:
        match constr_type.__reduce__():
            case (_, (_, (arg_types, result_type))):
                def __new__(cls, *_data):
                    obj = object.__new__(cls)
                    obj._constr_ = type(cls)
                    return obj

                def __init__(self, *data):
                    if len(data) != len(arg_types):
                        raise TypeError(f"{gadt_cls.__name__}.{constr_name} takes exactly {len(arg_types)} "
                                        f"argument{'s' if len(arg_types) != 1 else ''} "
                                        f"({len(data)} given)")
                    self._construction_data_ = data
                    self._constr_name_ = constr_name
                    self._constr_type_ = constr_type

                    for i, datum in enumerate(data):
                        setattr(self, f"_construction_data_{i}", datum)

                cls_bases: tuple[type, ...] = (gadt_cls,)
                cls_namespace = dict(gadt_cls.__dict__)
                cls_namespace.update({
                    "__annotations__": {
                        "_arity_": int,
                        "_origin_": GADT,
                        "_name_": str,
                        "_type_": _CompoundConstrType,
                        "_arg_types_": tuple[type, ...],
                        "_result_type_": type
                    },
                    "__new__": __new__,
                    "__init__": __init__,
                    "__match_args__": tuple(f"_construction_data_{i}" for i in range(len(arg_types))),
                    "_arity_": len(arg_types),
                    "_origin_": gadt_cls,
                    "_name_": constr_name,
                    "_type_": constr_type,
                    "_arg_types_": tuple(arg_types),
                    "_result_type_": result_type
                })
                return constr_name, cls_bases, cls_namespace
            case _:
                raise TypeError(f"Unexpected structure of ({constr_type}).__reduce__().")

    def __new__(mcs, gadt_cls: GADT, constr_name: str, constr_type: _CompoundConstrType) -> Self:
        return type.__new__(mcs, *CompoundConstructor._generate_type_init_args(gadt_cls, constr_name, constr_type))

    def __init__(cls, _gadt_cls: GADT, constr_name: str, constr_type: _CompoundConstrType):
        type.__init__(cls, *CompoundConstructor._generate_type_init_args(_gadt_cls, constr_name, constr_type))
