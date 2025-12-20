import sys
from typing import Set, Dict, Optional, Any
import rpyc

from .util import log
from .debug import DEBUG
from .proxy_generator import RemoteProxyGenerator, RemoteTypeMapper


class RPyCImportBridge:
    """Main orchestrator for RPyC import bridging."""

    def __init__(
        self,
        connection: rpyc.Connection,
        *,
        allow_private_attr_fallback: bool = True,
    ):
        """Initialize the import bridge with an RPyC connection.

        Args:
            connection: Active RPyC connection to remote Python instance
            allow_private_attr_fallback: Store private attrs locally if remote blocks
        """
        self.connection = connection
        self.registered_modules: Set[str] = set()
        self.allow_private_attr_fallback = allow_private_attr_fallback
        self.type_mapper = RemoteTypeMapper(connection)
        self.proxy_generator = RemoteProxyGenerator(
            connection,
            self.type_mapper,
            allow_private_attr_fallback=allow_private_attr_fallback,
            module_loader_factory=lambda remote_module, fullname: RemoteImportLoader(
                self, remote_module, fullname
            ),
        )
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

    def _build_spec(self, fullname: str, loader: Loader, is_package: bool):
        spec = importlib.machinery.ModuleSpec(
            fullname, loader, is_package=is_package
        )
        if is_package:
            spec.submodule_search_locations = []
        return spec

    def _is_package(self, remote_module: Any, fullname: str) -> bool:
        try:
            return hasattr(remote_module, "__path__")
        except Exception as e:
            error_msg = f"unexpected error checking if {fullname} is package: {e}"
            if DEBUG:
                log(error_msg)
            raise ImportError(error_msg) from e

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
        root_module = parts[0]

        # only handle registered modules
        if root_module not in self.bridge.registered_modules:
            return None

        # handle root module import (e.g., "sample_module")
        if len(parts) == 1:
            try:
                # check if remote module exists
                remote_module = getattr(self.bridge.connection.root, root_module, None)
                if remote_module is None:
                    error_msg = (
                        f"module {root_module} is registered but not available on server. "
                        f"add 'def exposed_{root_module}(self): import {root_module}; return {root_module}' "
                        f"to your rpyc service"
                    )
                    raise ImportError(error_msg)

                # create loader for root module
                loader = RemoteImportLoader(self.bridge, remote_module, fullname)
                is_package = self._is_package(remote_module, fullname)
                spec = self._build_spec(fullname, loader, is_package)
                return spec

            except ImportError:
                # re-raise import errors as they contain useful messages
                raise
            except Exception as e:
                # unexpected errors should be loud
                error_msg = f"unexpected error importing {fullname}: {e}"
                if DEBUG:
                    log(error_msg)
                raise ImportError(error_msg) from e

        # handle submodule import (e.g., "sample_module.something" or deeper)
        if len(parts) < 2:
            return None

        try:
            # check if we have import helper - needed for deep imports
            try:
                has_import_module = hasattr(self.bridge.connection.root, "import_module")
            except Exception as e:
                error_msg = f"unexpected error checking import helper for {fullname}: {e}"
                if DEBUG:
                    log(error_msg)
                raise ImportError(error_msg) from e

            if not has_import_module:
                error_msg = (
                    f"cannot import submodule {fullname}: "
                    f"server does not expose 'import_module' method. "
                    f"add 'def exposed_import_module(self, module_name): "
                    f"import importlib; return importlib.import_module(module_name)' "
                    f"to your rpyc service"
                )
                raise ImportError(error_msg)

            # first, try to import the full path on remote side to test if it's a real module
            try:
                remote_module = self.bridge.connection.root.import_module(fullname)
                
                # check if it's actually a module (has __file__ or __path__)
                is_real_module = (
                    hasattr(remote_module, "__file__")
                    or hasattr(remote_module, "__path__")
                    or getattr(remote_module, "__spec__", None) is not None
                )
                
                if not is_real_module:
                    # this is likely a function/class/variable, not a module
                    # let python handle it via the parent module's __getattr__
                    if DEBUG:
                        log(f"{fullname} is not a real module (no __file__ or __path__)")
                    return None
                
                # it's a real module, create a loader for it
                loader = RemoteImportLoader(self.bridge, remote_module, fullname)
                is_package = self._is_package(remote_module, fullname)
                spec = self._build_spec(fullname, loader, is_package)
                return spec
                
            except ImportError as import_err:
                # the full path doesn't exist as a module on remote
                # this is normal - it means the last part is likely an attribute
                if DEBUG:
                    log(f"remote import of {fullname} failed: {import_err}")
                return None
            except Exception as e:
                # unexpected error during remote import
                error_msg = f"unexpected error testing remote import of {fullname}: {e}"
                if DEBUG:
                    log(error_msg)
                raise ImportError(error_msg) from e

        except ImportError:
            # re-raise import errors as they contain useful messages
            raise
        except Exception as e:
            # unexpected errors should be loud
            error_msg = f"unexpected error in import finder for {fullname}: {e}"
            if DEBUG:
                log(error_msg)
            raise ImportError(error_msg) from e


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

        # preserve import system metadata before updating
        original_spec = getattr(module, "__spec__", None)
        original_loader = getattr(module, "__loader__", None)

        # copy attributes to actual module
        module.__dict__.update(proxy_module.__dict__)

        # set proper module metadata
        if hasattr(module, "__path__"):
            module.__package__ = self.fullname
        else:
            module.__package__ = self.fullname.rpartition(".")[0]

        # restore import system metadata
        if original_spec is not None:
            module.__spec__ = original_spec
        if original_loader is not None:
            module.__loader__ = original_loader
