"""Start one readsb network relay using its root-rendered non-secret config."""
import json
import os
from pathlib import Path
import sys
from .aggregators import provider, relay_args

if __name__ == "__main__":
    key = sys.argv[1]
    provider(key)
    entry = json.loads((Path("/etc/airnode/providers") / (key + ".json")).read_text())
    args = relay_args(key, entry)
    os.execv(args[0], args)
