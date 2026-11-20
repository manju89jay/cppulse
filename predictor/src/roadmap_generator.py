"""Compatibility alias for cppulse.predictor.roadmap_generator."""

from importlib import import_module
import sys

_canonical = import_module("cppulse.predictor.roadmap_generator")
# Preserve module identity so legacy monkeypatches affect canonical callers.
sys.modules[__name__] = _canonical
