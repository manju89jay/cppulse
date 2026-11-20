"""Compatibility entry point for conservative flat-output archive import."""

from cppulse.importer import import_pipeline, main

__all__ = ["import_pipeline", "main"]

if __name__ == "__main__":
    main()
