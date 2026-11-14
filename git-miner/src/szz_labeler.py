"""Compatibility alias for cppulse.git_miner.szz_labeler."""

from importlib import import_module
import sys

_canonical = import_module("cppulse.git_miner.szz_labeler")
# Preserve module identity so legacy monkeypatches affect canonical callers.
sys.modules[__name__] = _canonical
