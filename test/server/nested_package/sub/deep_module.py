# deep nested module

def deep_function(x):
    return f"deep: {x}"

class DeepClass:
    def __init__(self, value="deep"):
        self.value = value
    
    def get_deep(self):
        return f"very {self.value}"