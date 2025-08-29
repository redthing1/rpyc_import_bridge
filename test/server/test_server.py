import sys
import threading
import time
from pathlib import Path
import rpyc
from rpyc.utils.server import ThreadedServer

# add cwd to path to allow local import
tests_dir = Path(__file__).parent
sys.path.insert(0, str(tests_dir))

try:
    import numpy

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


class TestService(rpyc.Service):
    @property
    def exposed_sample_module(self):
        import sample_module

        return sample_module

    @property
    def exposed_numpy(self):
        if HAS_NUMPY:
            return numpy
        raise ImportError("numpy not available")
    
    @property
    def exposed_test_package(self):
        import test_package
        return test_package
    
    def exposed_import_module(self, module_name):
        """Import a module on the server side and return it."""
        import importlib
        return importlib.import_module(module_name)
    
    @property
    def exposed_advanced_classes(self):
        import advanced_classes
        return advanced_classes
    
    @property 
    def exposed_data_types(self):
        import data_types
        return data_types
    
    @property
    def exposed_nested_package(self):
        import nested_package
        return nested_package


class TestServer:
    def __init__(self):
        self.server = None
        self.port = None

    def start(self):
        self.server = ThreadedServer(
            TestService(), port=6070, protocol_config={"allow_all_attrs": True}
        )
        self.port = self.server.port
        print(f"starting server on port {self.port}")
        self.server.start()


if __name__ == "__main__":
    server = TestServer()
    server.start()
