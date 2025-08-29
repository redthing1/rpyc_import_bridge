# advanced class testing module
# tests inheritance, properties, various method types

class BaseClass:
    """A base class for testing inheritance."""
    base_attr = "base_value"
    
    def __init__(self, value=10):
        self.value = value
    
    def base_method(self):
        return f"base: {self.value}"
    
    @classmethod
    def create_default(cls):
        return cls(42)
    
    @staticmethod
    def static_helper(x):
        return x * 100

class DerivedClass(BaseClass):
    """A derived class for testing inheritance."""
    
    def __init__(self, value=20, extra=None):
        super().__init__(value)
        self.extra = extra
    
    def base_method(self):
        # override parent method
        return f"derived: {self.value}"
    
    def derived_only_method(self):
        return f"extra: {self.extra}"
    
    @property
    def computed_property(self):
        return self.value + (self.extra or 0)
    
    @computed_property.setter
    def computed_property(self, val):
        self.value = val
        self.extra = 0

class PropertyClass:
    """Test various property patterns."""
    
    def __init__(self):
        self._private = 0
    
    @property
    def read_only(self):
        return self._private + 100
    
    @property
    def read_write(self):
        return self._private
    
    @read_write.setter
    def read_write(self, value):
        self._private = value

class SpecialMethodsClass:
    """Test special methods that are commonly used."""
    
    def __init__(self, items=None):
        self.items = list(items or [])
    
    def __len__(self):
        return len(self.items)
    
    def __getitem__(self, index):
        return self.items[index]
    
    def __setitem__(self, index, value):
        self.items[index] = value
    
    def __contains__(self, item):
        return item in self.items
    
    def __iter__(self):
        return iter(self.items)
    
    def __str__(self):
        return f"SpecialClass({self.items})"
    
    def __repr__(self):
        return f"SpecialMethodsClass({self.items!r})"
    
    def __call__(self, new_item):
        self.items.append(new_item)
        return len(self.items)

# decorator testing
def simple_decorator(func):
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        return f"decorated: {result}"
    return wrapper

@simple_decorator
def decorated_function(x):
    return x * 2

# context manager testing
class SimpleContextManager:
    def __init__(self, name):
        self.name = name
        self.entered = False
    
    def __enter__(self):
        self.entered = True
        return f"entered {self.name}"
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.entered = False
        return False  # don't suppress exceptions

# generator testing
def simple_generator(n):
    for i in range(n):
        yield i * 2

def fibonacci_generator():
    a, b = 0, 1
    while True:
        yield a
        a, b = b, a + b