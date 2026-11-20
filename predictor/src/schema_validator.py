"""Compatibility alias for cppulse.predictor.schema_validator."""

from importlib import import_module
import sys

_canonical = import_module("cppulse.predictor.schema_validator")
# Preserve module identity so legacy monkeypatches affect canonical callers.
sys.modules[__name__] = _canonical
