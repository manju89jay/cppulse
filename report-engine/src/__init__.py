"""Legacy component-local imports, backed by the canonical cppulse package."""

from pathlib import Path
import sys

# Support the existing ``cd report-engine && python -m src.pdf_generator``
# checkout command without requiring an editable installation or PYTHONPATH.
_source_package = Path(__file__).resolve().parents[2] / "python"
if _source_package.is_dir() and str(_source_package) not in sys.path:
    sys.path.insert(0, str(_source_package))
