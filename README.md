# rpyc import bridge

import modules over rpyc.

this is a terrible hack and nobody should use it.

## client

```py
from rpyc_import_bridge import ImportBridge

bridge = ImportBridge(rpyc_connection)

# imports now work naturally
from numpy import array
from mymodule.things import Function
```

by default, the bridge only intercepts modules that are missing locally.
pass module names to force remote even if a local copy exists:

```py
bridge = ImportBridge(rpyc_connection, "mypackage1", "mypackage2")
```

## server

```py
class Service(rpyc.Service):
    def exposed_import_module(self, module_name):
        import importlib
        return importlib.import_module(module_name)
```

## testing

```sh
uv run python ./test/server/test_server.py
uv run python ./test/client/test_suite.py
```
