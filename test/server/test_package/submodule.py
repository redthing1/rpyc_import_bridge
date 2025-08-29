# Test submodule for package import testing
# This simulates binaryninja.mediumlevelil or similar

def submodule_function(x, y):
    """A function in a submodule."""
    return x * y

class SubmoduleClass:
    """A class in a submodule."""
    def __init__(self, multiplier=2):
        self.multiplier = multiplier
    
    def multiply(self, value):
        return value * self.multiplier

# Some module-level constants
SUBMODULE_CONSTANT = "I am a constant"
MAGIC_NUMBER = 42