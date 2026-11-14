"""Compatibility alias for cppulse.predictor.feature_engineer."""

from importlib import import_module
import sys

_canonical = import_module("cppulse.predictor.feature_engineer")
# Preserve module identity so legacy monkeypatches affect canonical callers.
sys.modules[__name__] = _canonical
