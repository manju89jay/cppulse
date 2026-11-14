"""Measured normalization tests using labeled synthetic execution contracts."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any

import pytest

from cppulse.analysis import normalize_native_analysis, persist_native_analysis
from cppulse.contracts import validate
from cppulse.errors import ContractError
from test_analysis_inventory import native_snapshot
from tests.test_maintenance_metrics_contract import native_metric_report


def add_metrics(report: dict[str, Any], root: Path) -> None:
    """Attach the measured raw test shape to the existing closed fixture."""
    raw = deepcopy(native_metric_report()['metadata']['analysis']['native_metrics'])
    raw['files'][0]['path'] = str(root / 'main.cpp')
    raw['files'][0]['source_content_sha256'] = hashlib.sha256((root / 'main.cpp').read_bytes()).hexdigest()
    report['metadata']['analysis']['native_metrics'] = raw


def test_native_measured_cells_have_distinct_stable_file_function_context_ids(tmp_path: Path) -> None:
    snapshot, selection = native_snapshot(tmp_path, mutate=add_metrics)
    result = normalize_native_analysis(snapshot, **selection)
    validate('analysis_metrics', result.metrics)
    metrics = result.metrics
    assert metrics['analysis_inventory_id'] == result.inventory['id']
    assert metrics['job_context_id'] == 'native'
    assert all(row['file'] == 'main.cpp' for row in metrics['items'])
    assert len({row['id'] for row in metrics['items']}) == len(metrics['items'])
    assert {row['context_id'] for row in metrics['items']} == {result.inventory['items'][0]['parse_context_id']}
    values = {(row['symbol'], row['metric']): row['value'] for row in metrics['items']}
    assert values[(None, 'physical_loc')] == 1
    assert values[('c:@F@a#', 'cyclomatic_complexity')] == 1
    assert result.metrics == normalize_native_analysis(snapshot, **selection).metrics


def test_missing_legacy_metrics_remain_missing(tmp_path: Path) -> None:
    snapshot, selection = native_snapshot(tmp_path)
    assert normalize_native_analysis(snapshot, **selection).metrics is None


def test_actual_buffer_digest_must_agree_with_frozen_native_input(tmp_path: Path) -> None:
    def mutate(report: dict[str, Any], root: Path) -> None:
        add_metrics(report, root)
        report['metadata']['analysis']['native_metrics']['files'][0]['source_content_sha256'] = 'f' * 64
    snapshot, selection = native_snapshot(tmp_path, mutate=mutate)
    with pytest.raises(ContractError, match='buffer|content|digest'):
        normalize_native_analysis(snapshot, **selection)


def test_publication_retains_metrics_as_a_typed_immutable_artifact(tmp_path: Path) -> None:
    snapshot, selection = native_snapshot(tmp_path, mutate=add_metrics)
    derived = persist_native_analysis(snapshot, workspace=tmp_path, store=tmp_path / 'store', **selection)
    derived.verify()
    descriptors = [row for row in derived.manifest['artifacts'] if row.get('contract', {}).get('kind') == 'analysis_metrics']
    assert len(descriptors) == 1
    document = derived.read_json(descriptors[0]['id'])
    assert document['job_context_id'] == 'native'
    assert any(row['metric'] == 'cyclomatic_complexity' for row in document['items'])
