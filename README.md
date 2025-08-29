
# rpyc import bridge

import modules over rpyc.

this is a terrible hack and nobody should use it.

## example

```py
bridge = RPyCImportBridge(rpyc_connection)
bridge.register_remote_module('numpy')
bridge.register_remote_module('mymodule')
bridge.install_import_hooks()

# imports now work naturally
from numpy import array
from mymodule.things import Function
```

## testing

```sh
uv run python ./test/server/test_server.py
uv run python ./test/client/test_suite.py
```
