# data types testing module
# tests various data types and structures

import json
from collections import defaultdict, namedtuple
from dataclasses import dataclass
from typing import List, Dict, Optional

# basic data structures
SIMPLE_LIST = [1, 2, 3, "hello", True, None]
SIMPLE_DICT = {
    "string": "value", 
    "number": 42, 
    "list": [1, 2, 3],
    "nested": {"inner": "value"}
}
SIMPLE_TUPLE = (1, "two", 3.0)
SIMPLE_SET = {1, 2, 3, "unique"}

# more complex structures
NESTED_STRUCTURE = {
    "level1": {
        "level2": {
            "level3": ["deep", "nesting", {"very": "deep"}]
        },
        "list_of_dicts": [
            {"id": 1, "name": "first"},
            {"id": 2, "name": "second"}
        ]
    },
    "top_level_list": [
        {"mixed": [1, "two", {"three": 3}]},
        [1, [2, [3, [4]]]]
    ]
}

# collections module types
DEFAULT_DICT = defaultdict(list)
DEFAULT_DICT["key1"].extend([1, 2, 3])
DEFAULT_DICT["key2"].append("value")

Point = namedtuple("Point", ["x", "y"])
NAMED_TUPLE = Point(10, 20)

# dataclasses (python 3.7+)
@dataclass
class Person:
    name: str
    age: int
    email: Optional[str] = None
    
    def greet(self):
        return f"Hello, I'm {self.name}, age {self.age}"

PERSON_INSTANCE = Person("Alice", 30, "alice@example.com")

# functions that return various data types
def get_large_list(size=1000):
    return list(range(size))

def get_nested_dict(depth=3):
    if depth <= 0:
        return "leaf"
    return {"level": depth, "child": get_nested_dict(depth - 1)}

def get_json_data():
    return json.dumps({
        "users": [
            {"id": i, "name": f"user_{i}", "active": i % 2 == 0}
            for i in range(10)
        ],
        "metadata": {
            "created": "2024-01-01",
            "version": "1.0"
        }
    })

class DataContainer:
    """Class that holds various data types."""
    
    def __init__(self):
        self.strings = ["hello", "world", "testing"]
        self.numbers = [1, 2.5, 3, 4.7]
        self.mixed_list = [1, "two", 3.0, [4, 5], {"six": 6}]
        self.lookup = {str(i): i**2 for i in range(10)}
    
    def get_all_data(self):
        return {
            "strings": self.strings,
            "numbers": self.numbers,
            "mixed": self.mixed_list,
            "lookup": self.lookup
        }
    
    def add_item(self, collection_name, item):
        if hasattr(self, collection_name):
            collection = getattr(self, collection_name)
            if isinstance(collection, list):
                collection.append(item)
            elif isinstance(collection, dict):
                # assume item is (key, value) tuple
                key, value = item
                collection[key] = value
        return getattr(self, collection_name)

# exception testing
class CustomError(Exception):
    """Custom exception for testing error handling."""
    def __init__(self, message, error_code=None):
        super().__init__(message)
        self.error_code = error_code

def function_that_raises():
    raise CustomError("Something went wrong", error_code=500)

def function_with_nested_exception():
    try:
        function_that_raises()
    except CustomError as e:
        raise RuntimeError("Wrapped error") from e