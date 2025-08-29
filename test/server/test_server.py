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
