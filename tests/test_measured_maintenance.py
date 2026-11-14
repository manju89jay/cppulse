"""Pure consumer tests; synthetic calculations do not qualify native execution."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from cppulse.contracts import validate
from cppulse.errors import ContractError
from cppulse.maintenance import compute_maintenance_health
from cppulse.tooling import load_rule_registry
from tests.test_maintenance_metrics_contract import bound_metric_bundle


def inputs() -> dict[str, Any]:
    """Build explicit measured facts for the 1 KLOC hand calculation."""
    bundle = bound_metric_bundle()
    inventory = bundle['analysis_inventory']
    registry = load_rule_registry()
    rules = [row['id'] for row in registry['rules'] if row['category'] != 'misra']
    inventory['requested_rules'] = rules
    inventory['enabled_rules'] = rules
    inventory['items'][0]['executed_rules'] = rules
    metrics = bundle['analysis_metrics']
    metrics['items'][0]['value'] = 1000
    metrics['items'][1]['value'] = 600
    observations = bundle['observations']
    seed = observations['items'][0]
    observations['items'] = []
    for rule, count in [('CPP-MEM-001', 1), ('CPP-CX-001', 2), ('CPP-MOD-001', 5)]:
        definition = next(row for row in registry['rules'] if row['id'] == rule)
        for index in range(count):
            row = deepcopy(seed)
            row.update(id=f'{rule}-{index}', rule_id=rule, rule_version=definition['version'])
            observations['items'].append(row)
    inventory['items'][0]['finding_count'] = len(observations['items'])
    return dict(source_digest=metrics['source_digest'], inventories=[inventory],
                metrics=[metrics], observations=[observations], registry=registry,
                required_context_ids=['native'])


def test_physical_kloc_equations_are_unrounded_and_pin_exact_rule_versions() -> None:
    result = compute_maintenance_health(**inputs())
    validate('maintenance_health', result)
    assert result['aggregate']['overall'] == pytest.approx(81.81818181818181)
    assert result['aggregate']['by_category'] == {'memory_safety':80, 'complexity':80, 'modernization':90}
    assert result['contexts'][0]['physical_loc'] == 1000
    assert result['scorer']['required_rule_versions']['CPP-CX-001'] == 'prototype-2'


def test_job_contexts_are_distinct_from_per_file_parse_contexts() -> None:
    result = compute_maintenance_health(**inputs())
    assert result['required_context_ids'] == ['native']
    assert [row['job_context_id'] for row in result['contexts']] == ['native']


@pytest.mark.parametrize('gap', ['missing_required', 'missing_metric', 'partial', 'disabled', 'inferred', 'fallback', 'zero_loc', 'missing_function_cell'])
def test_incomplete_required_scope_never_gets_a_full_score(gap: str) -> None:
    data = inputs()
    row = data['inventories'][0]['items'][0]
    if gap == 'missing_required':
        data['required_context_ids'].append('unobserved-job')
    elif gap == 'missing_metric':
        data['metrics'][0]['items'].pop(0)
    elif gap == 'partial':
        row.update(status='partial', error_count=1, executed_rules=[])
        for metric in data['metrics'][0]['items']:
            metric.update(availability='unavailable', value=None, limitations=['Partial native parse.'])
    elif gap == 'disabled':
        data['inventories'][0]['enabled_rules'].remove('CPP-MEM-001')
        row['executed_rules'].remove('CPP-MEM-001')
    elif gap == 'inferred':
        row.update(context_source='inferred', context_match='unverified')
    elif gap == 'fallback':
        row.update(context_source='fallback', context_match='unverified')
    elif gap == 'zero_loc':
        data['metrics'][0]['items'][0]['value'] = 0
        data['metrics'][0]['items'][1]['value'] = 0
    else:
        data['metrics'][0]['items'][2]['value'] = 1
    result = compute_maintenance_health(**data)
    assert result['aggregate']['overall'] is None
    assert result['aggregate']['worst_context_id'] is None
    assert set(result['aggregate']['by_category'].values()) == {None}
    assert result['aggregate']['limitations']
    validate('maintenance_health', result)


def test_inferred_explicit_optin_is_maintenance_only_and_changes_method_digest() -> None:
    data = inputs()
    data['inventories'][0]['items'][0].update(context_source='inferred', context_match='unverified')
    default = compute_maintenance_health(**data)
    allowed = compute_maintenance_health(**data, allow_inferred_parse=True)
    assert allowed['aggregate']['overall'] is not None
    assert allowed['contexts'][0]['limitations']
    assert allowed['consumer_assurance'] == 'not_assessed'
    assert default['scorer']['configuration_digest'] != allowed['scorer']['configuration_digest']


def test_optional_context_does_not_hide_a_missing_required_context() -> None:
    data = inputs()
    data['required_context_ids'] = ['missing']
    data['optional_context_ids'] = ['native']
    result = compute_maintenance_health(**data)
    assert result['aggregate']['overall'] is None
    assert result['aggregate']['incomplete_required_context_ids'] == ['missing']
    assert result['contexts'][0]['overall'] is not None


def test_empty_inputs_do_not_receive_100() -> None:
    data = inputs()
    data.update(inventories=[], metrics=[], observations=[])
    result = compute_maintenance_health(**data)
    assert result['aggregate']['overall'] is None
    assert result['aggregate']['availability'] == 'no_data'


def test_conflicting_registry_versions_cannot_be_scored() -> None:
    data = inputs()
    data['observations'][0]['items'][0]['rule_version'] = 'invented'
    with pytest.raises(ContractError, match='version'):
        compute_maintenance_health(**data)


def test_source_mismatch_cannot_be_scored() -> None:
    data = inputs()
    data['metrics'][0]['source_digest'] = 'b' * 64
    with pytest.raises(ContractError, match='source'):
        compute_maintenance_health(**data)


def test_reordered_inputs_have_same_deterministic_result() -> None:
    data = inputs()
    first = compute_maintenance_health(**data)
    data['metrics'][0]['items'].reverse()
    data['observations'][0]['items'].reverse()
    data['registry']['rules'].reverse()
    assert compute_maintenance_health(**data) == first
