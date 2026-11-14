"""Compatibility alias for cppulse.git_miner.commit_utils."""

from importlib import import_module
import sys

_canonical = import_module("cppulse.git_miner.commit_utils")
# Preserve module identity so legacy monkeypatches affect canonical callers.
sys.modules[__name__] = _canonical
