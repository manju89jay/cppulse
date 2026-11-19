"""Build the portable text-only candidate skill; performs no publication."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import zipfile

FILES = (
    "SKILL.md",
    "VERSION",
    "LICENSE",
    "references/commands.md",
    "references/commands.json",
    "references/interpretation.md",
)
MAX_FILE_BYTES = 64 * 1024
MAX_TOTAL_BYTES = 256 * 1024


def package_skill(source: Path, output: Path) -> str:
    """Write one deterministic ZIP of approved bounded UTF-8 files exclusively.

    Args:
        source: Skill source root with its fixed approved relative files.
        output: New local ZIP path; existing files are never overwritten.

    Returns:
        SHA-256 of the resulting archive.

    Raises:
        ValueError: A required file is unsafe, non-text or exceeds its budget.
    """
    payloads = []
    for name in FILES:
        path = source / name
        if any(parent.is_symlink() for parent in [path, *path.parents]):
            raise ValueError("Skill source may not traverse symlinks")
        with path.open("rb") as stream:
            content = stream.read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES or b"\0" in content:
            raise ValueError("Skill source exceeds its text-only byte budget")
        try:
            content.decode("utf-8")
        except UnicodeError as error:
            raise ValueError("Skill source must be UTF-8 text") from error
        payloads.append((name, content))
    if sum(len(content) for _, content in payloads) > MAX_TOTAL_BYTES:
        raise ValueError("Skill package exceeds its total byte budget")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(payloads):
                entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                entry.external_attr = 0o100644 << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, content)
    return hashlib.sha256(output.read_bytes()).hexdigest()


def main() -> None:
    """Build an explicit local candidate archive and print its checksum."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(package_skill(Path(__file__).resolve().parent, args.output))


if __name__ == "__main__":
    main()
