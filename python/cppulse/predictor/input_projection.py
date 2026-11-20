"""Checked legacy feature inputs without retaining native token subtrees."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
from typing import Any, Iterator

from cppulse.contracts.json_projection import ProjectionLimits
from cppulse.contracts.json_stream import JsonStreamLimits
from cppulse.errors import IntegrityError
from cppulse.native_report_reader import open_native_report
from cppulse.native_projection_store import ProjectionStoreLimits
from cppulse.streamed_native_metrics import validate_streamed_native_metrics
from .measured_hotspots import _reported_hotspot_claims


@dataclass(frozen=True)
class PredictorInputs:
    """Copied feature inputs and literal claims, with original byte provenance."""

    findings: dict[str, Any]
    measured_hotspot_metrics: dict[str, dict[str, Any]]
    report_sha256: str


def _identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev, value.st_ino, value.st_mode, value.st_size,
        value.st_mtime_ns, value.st_ctime_ns,
    )


@contextmanager
def open_predictor_inputs(
    path: Path,
    *,
    directory: Path,
    store_limits: ProjectionStoreLimits = ProjectionStoreLimits(),
) -> Iterator[PredictorInputs]:
    """Validate original bytes and retain only feature/roadmap-relevant data.

    The document/record profile matches retained work-unit ingestion; native
    producer and SDK wire limits are unchanged. Findings and analysis inventory
    remain materialized. This is not a whole-pipeline or arbitrary-scale bound.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as error:
        raise IntegrityError(f"Native predictor input is missing or unsafe: {path}") from error
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise IntegrityError("Native predictor input must remain a regular file")

        def guard() -> None:
            try:
                current = path.stat(follow_symlinks=False)
            except OSError as error:
                raise IntegrityError("Native predictor input disappeared") from error
            if _identity(os.fstat(stream.fileno())) != _identity(before) or _identity(current) != _identity(before):
                raise IntegrityError("Native predictor input changed during processing")

        guard()
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
        guard()
        stream.seek(0)
        directory.mkdir(parents=True, exist_ok=True)
        with open_native_report(
            stream,
            expected_sha256=digest,
            expected_size=before.st_size,
            directory=directory,
            source_guard=guard,
            projection_limits=ProjectionLimits(json_limits=JsonStreamLimits(
                max_bytes=256 * 1024**2,
                max_item_bytes=16 * 1024**2,
                max_array_items=10_000_000,
            )),
            store_limits=store_limits,
        ) as reader:
            document = reader.document
            analysis = document["metadata"].get("analysis")
            native = analysis.get("native_metrics") if analysis is not None else None
            header = (
                {key: value for key, value in native.items() if key != "files"}
                if native is not None else None
            )
            validate_streamed_native_metrics(
                reader.iter_analysis_files(), reader.iter_metric_files(),
                metrics_header=header, directory=directory,
            )
            claims = _reported_hotspot_claims(
                document, reader.iter_metric_files(),
                header.get("metric_version") if header is not None else None,
            )
            document["findings"] = list(reader.iter_findings())
            if analysis is not None:
                if "files" in analysis:
                    analysis["files"] = list(reader.iter_analysis_files())
                analysis.pop("native_metrics", None)
            yield PredictorInputs(document, claims, digest)
            guard()
