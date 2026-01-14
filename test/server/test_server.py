import sys
from pathlib import Path
import rpyc
from rpyc.utils.server import ThreadedServer

# add cwd to path to allow local import
tests_dir = Path(__file__).parent
sys.path.insert(0, str(tests_dir))


class TestService(rpyc.Service):
    def exposed_import_module(self, module_name):
        """Import a module on the server side and return it."""
        import importlib

        return importlib.import_module(module_name)


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
