"""Compatibility entry point for :mod:`cppulse.report_engine.pdf_generator`."""

import sys

from cppulse.report_engine import pdf_generator as _implementation

if __name__ == "__main__":
    sys.exit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
