import rpyc
from rpyc_import_bridge import ImportBridge

c = rpyc.connect("127.0.0.1", 6070)

print(f"conn root sample_module: {c.root.sample_module}")

# bridge hack
print("initializing bridge")
bridge = ImportBridge(c, "sample_module", "numpy")

# try importing
print("importing sample_module")
import sample_module

print(f"imported sample_module: {sample_module}")

# try doing stuff
print(f"dir(sample_module): {dir(sample_module)}")
from sample_module import simple_function

print(f"simple_function: {simple_function}")

val = simple_function(3)
assert val == 6, "simple_function failed"
print(f"simple_function passed: {val}")

# try importing numpy
import numpy

print(f"imported numpy: {numpy}")

# try doing stuff with numpy
import numpy as np

print(f"numpy array: {np.array([1, 2, 3])}")
print(f"numpy zeros: {np.zeros((3,3))}")
