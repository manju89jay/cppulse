"""Compatibility alias for cppulse.predictor.model."""

from importlib import import_module
import sys

_canonical = import_module("cppulse.predictor.model")
# Preserve module identity so legacy monkeypatches affect canonical callers.
sys.modules[__name__] = _canonical
