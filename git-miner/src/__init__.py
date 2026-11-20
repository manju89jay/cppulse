"""Checkout-only compatibility package for the canonical cppulse namespace."""

from pathlib import Path
import sys

# The legacy command runs from a known component checkout. Installed workflows
# import cppulse directly and never need this bootstrap or a filesystem search.
_checkout_python = Path(__file__).resolve().parents[2] / "python"
if _checkout_python.is_dir() and str(_checkout_python) not in sys.path:
    sys.path.insert(0, str(_checkout_python))
