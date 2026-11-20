"""Compatibility alias for :mod:`cppulse.report_engine.schema_validator`."""

import sys

from cppulse.report_engine import schema_validator as _implementation

sys.modules[__name__] = _implementation
