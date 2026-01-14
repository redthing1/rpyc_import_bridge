import importlib.machinery
from importlib.abc import Loader
import sys
from collections.abc import Iterable
from typing import Any, Optional, Set

import rpyc

from .debug import DEBUG
from .proxy_generator import RemoteProxyGenerator, RemoteTypeMapper
from .util import log


def _root_name(name: str) -> str:
    root = name.strip().split(".", 1)[0]
    if not root:
        raise ValueError("module name cannot be empty")
    return root


def _normalize_modules(*entries: Any) -> list[str]:
    roots: list[str] = []
    for entry in entries:
        if entry is None:
            continue
        if isinstance(entry, bytes):
            roots.append(_root_name(entry.decode()))
            continue
        if isinstance(entry, str):
            roots.append(_root_name(entry))
            continue
        if isinstance(entry, Iterable):
            for item in entry:
                roots.extend(_normalize_modules(item))
            continue
        raise TypeError(f"module name must be str or iterable, got {type(entry)}")
    return roots


class ImportBridge:
    """Import bridge that proxies remote modules over RPyC."""

    def __init__(
        self,
        connection: rpyc.Connection,
        *force: Any,
        allow_private_attr_fallback: bool = True,
        auto_missing: bool = True,
        install: bool = True,
    ):
        self.connection = connection
        self.allow_private_attr_fallback = allow_private_attr_fallback
        self.auto_missing = auto_missing
        self._forced_roots: Set[str] = set()
        self._remote_roots: Set[str] = set()
        self._missing_roots: Set[str] = set()
        self._finder: Optional["BridgeFinder"] = None
        self._installed = False

        self.type_mapper = RemoteTypeMapper(connection)
        self.proxy_generator = RemoteProxyGenerator(
            connection,
            self.type_mapper,
            allow_private_attr_fallback=allow_private_attr_fallback,
            module_loader_factory=lambda remote_module, fullname: BridgeLoader(
                self, remote_module, fullname
            ),
        )

        self.force(*force)
        if install:
            self.install()

    def force(self, *modules: Any) -> None:
        for name in _normalize_modules(*modules):
            self._forced_roots.add(name)
            self._remote_roots.discard(name)
            self._missing_roots.discard(name)
        if DEBUG and modules:
            log(f"forced remote roots: {sorted(self._forced_roots)}")

    def unforce(self, *modules: Any) -> None:
        for name in _normalize_modules(*modules):
            self._forced_roots.discard(name)
        if DEBUG and modules:
            log(f"forced remote roots: {sorted(self._forced_roots)}")

    def clear_forced(self) -> None:
        self._forced_roots.clear()
        if DEBUG:
            log("cleared forced remote roots")

    def install(self) -> None:
        if self._installed:
            return
        self._finder = BridgeFinder(self)
        sys.meta_path.insert(0, self._finder)
        self._installed = True
        if DEBUG:
            log("installed import hooks")

    def uninstall(self) -> None:
        if not self._installed or not self._finder:
            return
        try:
            sys.meta_path.remove(self._finder)
        except ValueError:
            pass
        self._installed = False
        if DEBUG:
            log("uninstalled import hooks")

    def verify_connection(self) -> bool:
        try:
            _ = self.connection.root
            return not self.connection.closed
        except Exception:
            return False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.uninstall()


class BridgeFinder:
    """Meta path finder for remote module imports."""

    def __init__(self, bridge: ImportBridge):
        self.bridge = bridge

    def _has_import_module(self) -> bool:
        try:
            return hasattr(self.bridge.connection.root, "import_module")
        except Exception as exc:
            if DEBUG:
                log(f"import_module check failed: {exc}")
            return False

    def _import_remote(self, fullname: str, *, strict: bool) -> Optional[Any]:
        if not self._has_import_module():
            if strict:
                error_msg = (
                    "server does not expose 'import_module'. "
                    "add 'def exposed_import_module(self, module_name): "
                    "import importlib; return importlib.import_module(module_name)' "
                    "to your rpyc service"
                )
                raise ImportError(error_msg)
            return None
        try:
            return self.bridge.connection.root.import_module(fullname)
        except ImportError:
            if strict:
                raise
            return None
        except Exception as exc:
            if DEBUG:
                log(f"unexpected error importing {fullname}: {exc}")
            if strict:
                raise ImportError(
                    f"unexpected error importing {fullname}: {exc}"
                ) from exc
            return None

    def _build_spec(self, fullname: str, loader: "BridgeLoader", is_package: bool):
        spec = importlib.machinery.ModuleSpec(fullname, loader, is_package=is_package)
        if is_package:
            spec.submodule_search_locations = []
        return spec

    def _is_package(self, remote_module: Any, fullname: str) -> bool:
        try:
            return hasattr(remote_module, "__path__")
        except Exception as exc:
            error_msg = f"unexpected error checking if {fullname} is package: {exc}"
            if DEBUG:
                log(error_msg)
            raise ImportError(error_msg) from exc

    def _is_real_module(self, remote_module: Any) -> bool:
        try:
            return (
                hasattr(remote_module, "__file__")
                or hasattr(remote_module, "__path__")
                or getattr(remote_module, "__spec__", None) is not None
            )
        except Exception as exc:
            if DEBUG:
                log(f"unexpected error checking module type: {exc}")
            return False

    def _local_root_exists(self, root_module: str) -> bool:
        if root_module in sys.builtin_module_names:
            return True
        try:
            if importlib.machinery.BuiltinImporter.find_spec(root_module) is not None:
                return True
        except Exception:
            pass
        try:
            if importlib.machinery.FrozenImporter.find_spec(root_module) is not None:
                return True
        except Exception:
            pass
        try:
            if importlib.machinery.PathFinder.find_spec(root_module, None) is not None:
                return True
        except Exception:
            pass
        return False

    def _should_try_remote(self, root_module: str) -> bool:
        if root_module in self.bridge._missing_roots:
            return False
        if root_module in self.bridge._forced_roots:
            return True
        if root_module in self.bridge._remote_roots:
            return True
        if not self.bridge.auto_missing:
            return False
        if self._local_root_exists(root_module):
            return False
        return True

    def find_spec(self, fullname: str, path, target=None):
        root_module = fullname.split(".")[0]
        if not self._should_try_remote(root_module):
            return None

        strict = root_module in self.bridge._forced_roots
        try:
            remote_module = self._import_remote(fullname, strict=strict)
            if remote_module is None:
                if self.bridge.auto_missing and not strict and "." not in fullname:
                    self.bridge._missing_roots.add(root_module)
                return None

            if not self._is_real_module(remote_module):
                if DEBUG:
                    log(f"{fullname} is not a real module")
                return None

            if self.bridge.auto_missing and not strict:
                self.bridge._remote_roots.add(root_module)

            loader = BridgeLoader(self.bridge, remote_module, fullname)
            is_package = self._is_package(remote_module, fullname)
            return self._build_spec(fullname, loader, is_package)

        except ImportError:
            raise
        except Exception as exc:
            error_msg = f"unexpected error importing {fullname}: {exc}"
            if DEBUG:
                log(error_msg)
            raise ImportError(error_msg) from exc


class BridgeLoader(Loader):
    """Loader for remote modules."""

    def __init__(self, bridge: ImportBridge, remote_module: Any, fullname: str):
        self.bridge = bridge
        self.remote_module = remote_module
        self.fullname = fullname

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        if DEBUG:
            log(f"generating proxies for {self.fullname}")

        proxy_module = self.bridge.proxy_generator.create_proxy_module(
            self.remote_module, self.fullname
        )

        original_spec = getattr(module, "__spec__", None)
        original_loader = getattr(module, "__loader__", None)

        module.__dict__.update(proxy_module.__dict__)

        if hasattr(module, "__path__"):
            module.__package__ = self.fullname
        else:
            module.__package__ = self.fullname.rpartition(".")[0]

        if original_spec is not None:
            module.__spec__ = original_spec
        if original_loader is not None:
            module.__loader__ = original_loader
