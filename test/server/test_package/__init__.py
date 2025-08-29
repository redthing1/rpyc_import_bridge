# Test package for testing package imports
# This simulates packages like binaryninja that have submodules

package_version = "1.0.0"

def package_function(x):
    """A function at the package level."""
    return x + 100

class PackageClass:
    """A class at the package level."""
    def __init__(self, value=42):
        self.value = value
    
    def get_value(self):
        return self.value