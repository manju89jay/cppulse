"""Compatibility alias for :mod:`cppulse.report_engine.api`."""

import sys

from cppulse.report_engine import api as _implementation

sys.modules[__name__] = _implementation
