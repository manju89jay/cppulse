"""Copy the exact authored input into a fresh report path for the import control."""

from pathlib import Path


with Path('report.xml').open('xb') as stream:
    stream.write(Path('payload.xml').read_bytes())
