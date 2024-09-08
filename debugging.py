from __future__ import annotations

from pathlib import Path
from typing import Any

from persistent_singleton import persistent_singleton, PersistenceSource


# class TestMMCS(type):
#     pass
#
# class TestMCS(metaclass=TestMMCS):
#     pass

class TestSuper:
    pass


# @persistent_singleton(PersistenceSource.JSON, Path("store/persistent_singleton_test.json"))
# class Test(TestSuper):
#     test_str: str
#     test_int_list: list[int]
#     test_float_list: list[float]
#     test_test: Test
#     test_any: Any
#     test_string_annotated_bool: "bool"
#     test_int_default: int = 3
#     test_any_default: Any = "hi"
#
#     def __init__(self):
#         print("Hello world! I shouldn't exist!")


if __name__ == "__main__":
    pass
    # Test.test_int_default = 4
    # print(Test.test_int_default)
