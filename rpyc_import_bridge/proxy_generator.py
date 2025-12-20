import importlib
import sys
import types
import threading
from typing import Callable, Dict, Type, Optional, Any, Set
import rpyc

from .util import log
from .debug import DEBUG

# thread lock for proxy creation
_proxy_creation_lock = threading.Lock()


class RemoteTypeMapper:
    """Manages type relationships between local proxies and remote objects."""

    def __init__(self, connection: rpyc.Connection):
        self.connection = connection
        self.proxy_to_remote: Dict[Type, Dict[str, Any]] = {}
        self.remote_to_proxy: Dict[str, Type] = {}

    def register_proxy_type(
        self, proxy_class: Type, remote_module: str, remote_name: str
    ) -> None:
        """Register a proxy class and its remote counterpart.

        Args:
            proxy_class: Local proxy class
            remote_module: Remote module name (e.g., 'mymodule.submodule')
            remote_name: Remote class name (e.g., 'SubmoduleClass')
        """
        remote_info = {
            "module": remote_module,
            "name": remote_name,
            "fqn": f"{remote_module}.{remote_name}",
        }

        self.proxy_to_remote[proxy_class] = remote_info
        self.remote_to_proxy[remote_info["fqn"]] = proxy_class

        if DEBUG:
            log(f"registered proxy: {proxy_class.__name__} -> {remote_info['fqn']}")

    def is_netref(self, obj: Any) -> bool:
        """Check if an object is an RPyC netref.

        Args:
            obj: Object to check

        Returns:
            True if object is an RPyC netref
        """
        # rpyc netrefs have specific internal attributes
        return (
            hasattr(obj, "____conn__")
            or hasattr(obj, "____oid__")
            or hasattr(obj, "__class__")
            and hasattr(obj.__class__, "____conn__")
        )

    def check_isinstance(self, instance: Any, proxy_class: Type) -> bool:
        """Smart isinstance checking for remote objects.

        Args:
            instance: Object to check
            proxy_class: Proxy class to check against

        Returns:
            True if instance matches proxy_class type
        """
        # direct instance check first
        if type(instance) == proxy_class:
            return True

        # check if it's our proxy instance
        if hasattr(instance, "_remote_instance") and type(instance) == proxy_class:
            return True

        # get proxy info
        proxy_info = self.proxy_to_remote.get(proxy_class)
        if not proxy_info:
            return False

        # check if it's a netref
        if not self.is_netref(instance):
            return False

        try:
            # get remote type information
            instance_type = type(instance)
            remote_type_name = instance_type.__name__
            remote_module_name = getattr(instance_type, "__module__", "")

            # build possible full qualified names
            if remote_module_name:
                remote_fqn = f"{remote_module_name}.{remote_type_name}"
            else:
                remote_fqn = remote_type_name

            # check various matching patterns
            expected_name = proxy_info["name"]
            expected_fqn = proxy_info["fqn"]

            # pattern 1: exact FQN match
            if remote_fqn == expected_fqn:
                return True

            # pattern 2: FQN ends with our expected FQN (handles netref prefixes)
            if remote_fqn.endswith(expected_fqn):
                return True

            # pattern 3: just class name match
            if remote_type_name == expected_name:
                return True

            # pattern 4: remote type ends with our class name (handles qualifiers)
            if "." in remote_type_name and remote_type_name.endswith(
                f".{expected_name}"
            ):
                return True

            if DEBUG:
                log(f"isinstance failed: {expected_name} vs {remote_type_name}")

        except Exception as e:
            if DEBUG:
                log(f"isinstance check error for {proxy_class.__name__}: {e}")

        return False


class RemoteObjectProxy:
    """Base class for remote object proxies."""

    # class attributes set by proxy generator
    _remote_connection = None
    _remote_class = None
    _type_mapper = None
    _allow_private_attr_fallback = True
    _local_attrs = {
        "_remote_instance",
        "_remote_connection",
        "_remote_class",
        "_type_mapper",
        "_allow_private_attr_fallback",
    }

    def __init__(self, *args, **kwargs):
        """Create remote instance and store reference."""
        if self._remote_class is None:
            raise RuntimeError(
                f"proxy {self.__class__.__name__} not properly initialized"
            )

        # create actual remote object instance
        self._remote_instance = self._remote_class(*args, **kwargs)

    def __getattr__(self, name):
        """Forward attribute access to remote object."""
        try:
            return getattr(self._remote_instance, name)
        except Exception as e:
            raise type(e)(f"proxy forwarding failed for '{name}': {e}") from e

    def __setattr__(self, name, value):
        """Forward attribute setting to remote object."""
        if name in self._local_attrs:
            # keep internal attributes local
            object.__setattr__(self, name, value)
        else:
            # forward to remote
            try:
                setattr(self._remote_instance, name, value)
            except AttributeError as e:
                allow_fallback = getattr(self, "_allow_private_attr_fallback", True)
                if name.startswith("_") and allow_fallback:
                    # fallback for rpyc private-attr restrictions
                    object.__setattr__(self, name, value)
                    return
                raise AttributeError(
                    f"proxy forwarding failed for '{name}': {e}"
                ) from e
            except Exception as e:
                raise type(e)(f"proxy forwarding failed for '{name}': {e}") from e

    def __repr__(self):
        """Show that this is a proxy."""
        return f"<RemoteProxy for {self._remote_instance!r}>"

    def __str__(self):
        """Forward string representation."""
        return str(self._remote_instance)

    def __eq__(self, other):
        """Forward equality comparison."""
        if hasattr(other, "_remote_instance"):
            return self._remote_instance == other._remote_instance
        return self._remote_instance == other

    def __hash__(self):
        """Forward hashing."""
        return hash(self._remote_instance)

    def __bool__(self):
        """Forward boolean conversion."""
        return bool(self._remote_instance)

    def __call__(self, *args, **kwargs):
        """Forward function calls."""
        return self._remote_instance(*args, **kwargs)

    def __iter__(self):
        """Forward iteration."""
        return iter(self._remote_instance)

    def __len__(self):
        """Forward length."""
        return len(self._remote_instance)

    def __getitem__(self, key):
        """Forward indexing."""
        return self._remote_instance[key]

    def __setitem__(self, key, value):
        """Forward item setting."""
        self._remote_instance[key] = value


class RemoteProxyMetaclass(type):
    """Metaclass for proxy classes with isinstance support."""

    def __instancecheck__(cls, instance):
        """Custom isinstance check using type mapper."""
        if not hasattr(cls, "_type_mapper") or cls._type_mapper is None:
            # fallback to default isinstance
            return super().__instancecheck__(instance)

        return cls._type_mapper.check_isinstance(instance, cls)
    
    def __getattr__(cls, name):
        """Forward class-level attribute access to remote class."""
        # avoid infinite recursion on special attributes
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(f"type object '{cls.__name__}' has no attribute '{name}'")
        
        # forward to remote class for class methods, static methods, etc.
        if hasattr(cls, "_remote_class"):
            try:
                return getattr(cls._remote_class, name)
            except Exception as e:
                raise AttributeError(f"type object '{cls.__name__}' has no attribute '{name}'") from e
        
        raise AttributeError(f"type object '{cls.__name__}' has no attribute '{name}'")


def is_remote_class(member: Any) -> bool:
    """Check if a member is a class worth proxying.

    Args:
        member: Object to check

    Returns:
        True if member should be proxied
    """
    try:
        # must be a type/class
        if not isinstance(member, type):
            return False

        # get module name safely
        module_name = getattr(member, "__module__", "")
        if not module_name:
            return False

        # skip obvious builtin modules
        skip_modules = {
            "builtins",
            "typing",
            "collections",
            "abc",
            "_abc",
            "enum",
            "functools",
            "itertools",
            "operator",
            "re",
        }
        if module_name in skip_modules:
            return False

        # accept anything else as potentially worth proxying
        return True

    except Exception as e:
        if DEBUG:
            log(f"is_remote_class check failed for {member}: {e}")
        return False


def is_remote_module(member: Any) -> bool:
    """Check if a member looks like a module worth proxying."""
    try:
        if isinstance(member, types.ModuleType):
            return True
        if getattr(member, "__spec__", None) is not None:
            return True
        if hasattr(member, "__path__") or hasattr(member, "__file__"):
            return True
    except Exception as e:
        if DEBUG:
            log(f"is_remote_module check failed for {member}: {e}")
    return False


def create_proxy_class(
    connection: rpyc.Connection,
    remote_class: Any,
    class_name: str,
    module_name: str,
    type_mapper: RemoteTypeMapper,
    allow_private_attr_fallback: bool,
    base_class: Type = RemoteObjectProxy,
) -> Type:
    """Create a local proxy class for a remote class.

    Args:
        connection: RPyC connection
        remote_class: Remote class to proxy
        class_name: Name for the proxy class
        module_name: Module name (for isinstance tracking)
        type_mapper: Type mapper instance
        base_class: Base class for proxy

    Returns:
        New proxy class
    """
    # create class dictionary
    class_dict = {
        "_remote_connection": connection,
        "_remote_class": remote_class,
        "_type_mapper": type_mapper,
        "_allow_private_attr_fallback": allow_private_attr_fallback,
        "__module__": f"{module_name}.proxies",
        "__qualname__": class_name,
    }

    # create proxy class with custom metaclass
    proxy_class = RemoteProxyMetaclass(class_name, (base_class,), class_dict)

    # register with type mapper
    type_mapper.register_proxy_type(proxy_class, module_name, class_name)

    if DEBUG:
        log(f"created proxy {class_name} for {module_name}")

    return proxy_class


class RemoteProxyGenerator:
    """Generates proxy modules and classes for remote objects."""

    def __init__(
        self,
        connection: rpyc.Connection,
        type_mapper: RemoteTypeMapper,
        module_loader_factory: Optional[Callable[[Any, str], Any]] = None,
        allow_private_attr_fallback: bool = True,
    ):
        self.connection = connection
        self.type_mapper = type_mapper
        self.proxy_cache: Dict[str, Any] = {}
        self._module_loader_factory = module_loader_factory
        self._allow_private_attr_fallback = allow_private_attr_fallback

    def _register_proxy_module(
        self,
        remote_module: Any,
        module_name: str,
        cache_key: str,
        parent_module: types.ModuleType,
        attribute_name: str,
    ) -> types.ModuleType:
        existing = sys.modules.get(module_name)
        if existing is not None:
            self.proxy_cache[cache_key] = existing
            setattr(parent_module, attribute_name, existing)
            return existing

        proxy_module = self.create_proxy_module(remote_module, module_name)

        is_package = False
        try:
            is_package = hasattr(remote_module, "__path__")
        except Exception as e:
            if DEBUG:
                log(f"failed checking package status for {module_name}: {e}")
        if is_package:
            proxy_module.__package__ = module_name
        else:
            proxy_module.__package__ = module_name.rpartition(".")[0]

        loader = None
        if self._module_loader_factory is not None:
            loader = self._module_loader_factory(remote_module, module_name)

        spec = importlib.machinery.ModuleSpec(
            module_name, loader=loader, is_package=is_package
        )
        if is_package:
            spec.submodule_search_locations = []
        proxy_module.__spec__ = spec
        if loader is not None:
            proxy_module.__loader__ = loader

        sys.modules[module_name] = proxy_module
        self.proxy_cache[cache_key] = proxy_module
        setattr(parent_module, attribute_name, proxy_module)
        return proxy_module

    def create_proxy_module(
        self, remote_module: Any, module_name: str
    ) -> types.ModuleType:
        """Create a proxy module with JIT proxy class creation.

        Args:
            remote_module: Remote module object
            module_name: Full module name (e.g., 'mymodule.submodule')

        Returns:
            Module with JIT proxy support
        """
        # create new module
        proxy_module = types.ModuleType(module_name)
        proxy_module.__file__ = f"<proxy for {module_name}>"
        
        # check if remote module is a package (has __path__)
        is_package = False
        try:
            is_package = hasattr(remote_module, "__path__")
        except Exception as e:
            if DEBUG:
                log(f"failed checking package status for {module_name}: {e}")

        if is_package:
            # mark proxy module as a package too
            proxy_module.__path__ = []
            if DEBUG:
                log(f"marked proxy module {module_name} as package")

        # create JIT attribute getter
        def module_getattr(name: str):
            """Create proxies on-demand when classes are accessed."""
            # avoid infinite recursion on special attributes
            if name.startswith("__") and name.endswith("__"):
                raise AttributeError(
                    f"module '{module_name}' has no attribute '{name}'"
                )

            # check cache first
            cache_key = f"{module_name}.{name}"
            if cache_key in self.proxy_cache:
                return self.proxy_cache[cache_key]

            try:
                # check if remote module has the attribute
                missing = object()
                try:
                    member = getattr(remote_module, name)
                except AttributeError:
                    member = missing

                if member is missing:
                    if is_package:
                        expected_name = f"{module_name}.{name}"
                        try:
                            imported = importlib.import_module(expected_name)
                            self.proxy_cache[cache_key] = imported
                            setattr(proxy_module, name, imported)
                            return imported
                        except ModuleNotFoundError as e:
                            if e.name == expected_name:
                                raise AttributeError(
                                    f"module '{module_name}' has no attribute '{name}'"
                                ) from e
                            raise
                    raise AttributeError(
                        f"module '{module_name}' has no attribute '{name}'"
                    )

                if is_remote_module(member):
                    expected_name = f"{module_name}.{name}"
                    remote_name = None
                    try:
                        remote_name = getattr(member, "__name__", None)
                    except Exception:
                        remote_name = None

                    try:
                        imported = importlib.import_module(expected_name)
                        self.proxy_cache[cache_key] = imported
                        setattr(proxy_module, name, imported)
                        return imported
                    except ModuleNotFoundError as e:
                        if e.name == expected_name and remote_name == expected_name:
                            return self._register_proxy_module(
                                member, expected_name, cache_key, proxy_module, name
                            )
                        if e.name == expected_name:
                            # fall back to returning the original member
                            self.proxy_cache[cache_key] = member
                            setattr(proxy_module, name, member)
                            return member
                        raise
                    except ImportError as e:
                        if remote_name == expected_name:
                            return self._register_proxy_module(
                                member, expected_name, cache_key, proxy_module, name
                            )
                        raise
                if is_remote_class(member):
                    # thread-safe proxy creation
                    with _proxy_creation_lock:
                        # double-check cache
                        if cache_key in self.proxy_cache:
                            return self.proxy_cache[cache_key]

                        # create proxy class
                        proxy_class = create_proxy_class(
                            self.connection,
                            member,
                            name,
                            module_name,
                            self.type_mapper,
                            self._allow_private_attr_fallback,
                        )

                        # cache it
                        self.proxy_cache[cache_key] = proxy_class
                        setattr(proxy_module, name, proxy_class)

                        return proxy_class
                else:
                    # just return the member directly and cache it
                    self.proxy_cache[cache_key] = member
                    setattr(proxy_module, name, member)
                    return member

            except AttributeError:
                # re-raise attribute errors as-is
                raise
            except Exception as e:
                if DEBUG:
                    log(f"module getattr failed for {name}: {e}")
                # convert to attribute error for cleaner import failures
                raise AttributeError(
                    f"failed to access '{name}' in module '{module_name}': {e}"
                ) from e

        proxy_module.__getattr__ = module_getattr

        if DEBUG:
            log(f"created proxy module {module_name} with JIT support")

        return proxy_module
