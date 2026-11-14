"""Compatibility alias for cppulse.predictor.main."""

from importlib import import_module
import sys

_canonical = import_module("cppulse.predictor.main")
if __name__ == "__main__":
    _canonical.main()
else:
    sys.modules[__name__] = _canonical
