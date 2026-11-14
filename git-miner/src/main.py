"""Compatibility alias for cppulse.git_miner.main."""

from importlib import import_module
import sys

_canonical = import_module("cppulse.git_miner.main")
if __name__ == "__main__":
    _canonical.main()
else:
    sys.modules[__name__] = _canonical
