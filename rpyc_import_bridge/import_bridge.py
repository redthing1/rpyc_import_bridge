import sys
import threading
from typing import Set, Dict, Optional, Any
import rpyc

from .util import log
from .debug import DEBUG
from .proxy_generator import RemoteProxyGenerator, RemoteTypeMapper


class RPyCImportBridge:
    """Main orchestrator for RPyC import bridging."""

    def __init__(self, connection: rpyc.Connection):
        """Initialize the import bridge with an RPyC connection.

        Args:
            connection: Active RPyC connection to remote Python instance
        """
        self.connection = connection
        self.registered_modules: Set[str] = set()
        self.type_mapper = RemoteTypeMapper(connection)
        self.proxy_generator = RemoteProxyGenerator(connection, self.type_mapper)
        self.import_finder: Optional["RemoteImportFinder"] = None
        self._installed = False

    def register_remote_module(self, module_name: str) -> None:
        """Register a remote module for import bridging.

        Args:
            module_name: Top-level module name (e.g., 'mymodule', 'numpy')
        """
        if not isinstance(module_name, str):
            raise TypeError(f"Module name must be string, got {type(module_name)}")

        self.registered_modules.add(module_name)
        if DEBUG:
            log(f"registered remote module: {module_name}")

    def install_import_hooks(self) -> None:
        """Install Python import hooks for registered modules."""
        if self._installed:
            if DEBUG:
                log("import hooks already installed")
            return

        if not self.registered_modules:
            raise RuntimeError(
                "no modules registered, call register_remote_module() first"
            )

        # create and install the import finder
        self.import_finder = RemoteImportFinder(self)
        sys.meta_path.insert(0, self.import_finder)

        # create parent modules in sys.modules if needed
        self._ensure_parent_modules()

        self._installed = True
        if DEBUG:
            log(f"installed import hooks for {len(self.registered_modules)} modules")

    def uninstall_import_hooks(self) -> None:
        """Remove import hooks from sys.meta_path."""
        if not self._installed or not self.import_finder:
            return

        try:
            sys.meta_path.remove(self.import_finder)
        except ValueError:
            pass  # already removed

        self._installed = False
        if DEBUG:
            log("uninstalled import hooks")

    def _ensure_parent_modules(self) -> None:
        """Create parent module objects in sys.modules if needed."""
        import types

        for module_name in self.registered_modules:
            if module_name not in sys.modules:
                parent_module = types.ModuleType(module_name)
                parent_module.__path__ = []  # mark as package
                parent_module.__package__ = module_name
                sys.modules[module_name] = parent_module
                if DEBUG:
                    log(f"created parent module: {module_name}")

    def verify_connection(self) -> bool:
        """Verify that the RPyC connection is still active.

        Returns:
            True if connection is active, False otherwise
        """
        try:
            # simple test, access root
            _ = self.connection.root
            return not self.connection.closed
        except Exception:
            return False

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.uninstall_import_hooks()


import importlib.machinery
from importlib.abc import Loader


class RemoteImportFinder:
    """Meta path finder for remote module imports."""

    def __init__(self, bridge: RPyCImportBridge):
        self.bridge = bridge

    def find_spec(self, fullname: str, path, target=None):
        """Find module spec for registered remote modules.

        Args:
            fullname: Full module name (e.g., 'mymodule.submodule')
            path: Module path (unused)
            target: Target module (unused)

        Returns:
            ModuleSpec if we handle this module, None otherwise
        """
        # extract root module name
        parts = fullname.split(".")
        if len(parts) < 2:
            return None

        root_module = parts[0]

        # only handle registered modules
        if root_module not in self.bridge.registered_modules:
            return None

        submodule_name = parts[1]

        try:
            # check if remote module exists
            root_remote = getattr(self.bridge.connection.root, root_module, None)
            if root_remote is None:
                return None

            remote_module = getattr(root_remote, submodule_name, None)
            if remote_module is None:
                return None

            # verify it's module-like
            if not hasattr(remote_module, "__dict__"):
                if DEBUG:
                    log(f"remote object {fullname} is not module-like")
                return None

            # create loader for this module
            loader = RemoteImportLoader(self.bridge, remote_module, fullname)
            spec = importlib.machinery.ModuleSpec(fullname, loader)

            return spec

        except Exception as e:
            if DEBUG:
                log(f"import finder failed for {fullname}: {e}")
            return None


class RemoteImportLoader(Loader):
    """Loader for remote modules."""

    def __init__(self, bridge: RPyCImportBridge, remote_module: Any, fullname: str):
        self.bridge = bridge
        self.remote_module = remote_module
        self.fullname = fullname

    def create_module(self, spec):
        """Create the module (use default)."""
        return None

    def exec_module(self, module):
        """Execute/populate the module with proxy generation."""
        if DEBUG:
            log(f"generating proxies for {self.fullname}")

        # generate proxy module
        proxy_module = self.bridge.proxy_generator.create_proxy_module(
            self.remote_module, self.fullname
        )

        # copy attributes to actual module
        module.__dict__.update(proxy_module.__dict__)

        # set proper module metadata
        module.__package__ = self.fullname.rpartition(".")[0]
