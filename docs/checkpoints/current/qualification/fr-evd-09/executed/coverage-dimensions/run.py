"""Run the tracked finite coverage producer and qualify exact installed consumers."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import html
from importlib.util import find_spec
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

import cppulse
from cppulse import coverage
from cppulse.contracts import validate, validate_evaluation_policy
from cppulse.policy import evaluate_policy
from cppulse.run_store import RunStore
from cppulse.workflows import ensure_current_materials, read_documents


WORK = Path('/workspace/work')
LANE = Path(__file__).resolve().parent
GATES = WORK / 'git-scope-qualification/gates'
INSTALLED = GATES / 'candidate/installed'
TOOLS = WORK / 'coverage-tools/installed'
CLI = INSTALLED / 'bin/cppulse'
BUILD_TREE = 'da3f8f074ddbf5a89a9fd6d673f2b39b23b37bbe'
SOURCE_TREE = '4cf0194a3313412511a688e5924f7bb28939d94d'
WHEEL = 'db15edf7a6821442ea9b5321ffd3c9ca4d198e704c103cb1f6f044300c034700'
METHODS = {'lcov': {'line': 'lcov-da-v1', 'branch': 'lcov-brda-v1', 'function': 'lcov-fnda-v1'},
           'cobertura': {'line': 'cobertura-lines-v1', 'branch': 'cobertura-condition-counts-v1', 'function': 'lcov-fnda-v1'}}
COUNTS = {'lcov': {'line': (5, 8), 'branch': (1, 2), 'function': (2, 3)},
          'cobertura': {'line': (5, 8), 'branch': (1, 2)}}
STATUSES = {0: 'passed', 1: 'failed', 3: 'unknown'}
COVERAGE_LIMIT = 'Imported report contains measured counts but has no execution proof or current source verification.'


def sha(body):
    return hashlib.sha256(body).hexdigest()


def descriptor(body):
    return {'sha256': sha(body), 'size_bytes': len(body)}


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def pin(snapshot):
    return {'run_id': snapshot.run_id, 'manifest_sha256': snapshot.manifest_sha256}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def candidate():
    gates = GATES / 'test-freeze.json'
    artifact = GATES / 'candidate/artifact.json'
    source_freeze = WORK / 'governance-qualification/work-checks/freeze.json'
    frozen, manifest, source = (json.loads(path.read_bytes()) for path in (gates, artifact, source_freeze))
    for record in (frozen, manifest):
        assert record['candidate_tree'] == BUILD_TREE and record['wheel_sha256'] == WHEEL
    assert source['source_tree'] == SOURCE_TREE and source['tested_runtime_product_tree'] == BUILD_TREE
    assert frozen['candidate_manifest'] == str(artifact) and frozen['candidate_manifest_sha256'] == digest(artifact)
    assert manifest['installed'] == str(INSTALLED) and manifest['console'] == str(CLI)
    assert CLI.read_bytes().splitlines()[0] == b'#!/workspace/verification-python-venv/bin/python'
    assert digest(CLI) == manifest['console_sha256'] and digest(Path(manifest['wheel'])) == WHEEL
    return {'source_tree': SOURCE_TREE, 'wheel_build_tree': BUILD_TREE, 'wheel_sha256': WHEEL,
            'artifact_sha256': digest(artifact), 'test_freeze_sha256': digest(gates),
            'source_freeze_sha256': digest(source_freeze)}


def external(out, name, argv, expected):
    argv = [str(arg) for arg in argv]
    cwd = out / 'outside'
    actual = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=90, check=False)
    (out / f'{name}.stdout').write_bytes(actual.stdout)
    (out / f'{name}.stderr').write_bytes(actual.stderr)
    receipt = {'argv': argv, 'cwd': str(cwd), 'exit': actual.returncode}
    write_json(out / f'{name}.command.json', receipt)
    assert actual.returncode == expected, (name, actual.returncode, actual.stdout, actual.stderr)
    if expected == 2:
        assert actual.stderr.startswith(b'cppulse:') and not actual.stdout.strip(), name
        return receipt, actual.stderr.decode()
    return receipt, json.loads(actual.stdout)


def tool_scope():
    for module in ('gcovr', 'colorlog', 'lxml', 'pygments'):
        spec = find_spec(module)
        assert spec is not None and Path(spec.origin).resolve().is_relative_to(TOOLS), (module, spec)
    versions = json.loads((WORK / 'coverage-tools/verified-public-wheels.json').read_bytes())
    for path, record in versions.items():
        wheel = Path(path)
        assert wheel.stat().st_size == record['wheel_size'] and digest(wheel) == record['official_sha256']
    return {'official_wheels': {path: item['official_sha256'] for path, item in versions.items()},
            'record_sha256': digest(WORK / 'coverage-tools/verified-public-wheels.json')}


def select_tools(helper, fixture):
    requested = {'compiler': 'g++-14', 'gcov': 'gcov-14', 'gcovr': str(TOOLS / 'bin/gcovr'),
                 'cmake': 'cmake', 'ctest': 'ctest'}
    paths = {key: helper['selected_tool'](value) for key, value in requested.items()}
    assert paths['gcov'] == fixture['copied_gcov_source']
    assert paths['compiler'] == '/usr/bin/x86_64-linux-gnu-g++-14'
    assert paths['gcovr'] == str(TOOLS / 'bin/gcovr')
    assert all(paths[tool] == f'/workspace/cppulse/.venv/bin/{tool}' for tool in ('cmake', 'ctest'))
    return paths


def role(facts, receipt, direction, path):
    values = [row['artifact_id'] for row in facts[receipt]['binding'][f'{direction}_artifacts'] if row['path'] == path]
    assert len(values) == 1, (receipt, direction, path, values)
    return values[0]


def actual_raw(parent, workspace, selections):
    docs = read_documents(parent)
    executed = {fact['receipt']['id']: fact for fact in docs['execution_facts']}
    versions = {}
    for key, advertised in {'compiler-version': b'14.2.0', 'gcov-version': b'14.2.0',
                            'gcovr-version': b'gcovr 8.8', 'ctest-version': b'ctest version 3.31.6'}.items():
        fact = executed[key]
        assert fact['receipt']['status'] == 'passed' and fact['receipt']['exit_code'] == 0
        stream = parent.read_bytes(fact['binding']['log_artifacts']['stdout'])
        assert advertised in stream, (key, stream)
        versions[key] = stream.decode().splitlines()[0]
    assert executed['tests']['receipt']['tests'] == {'total': 1, 'passed': 1, 'failed': 0, 'skipped': 0, 'errors': 0}
    retained = {}
    for step, filename in [('compile', 'build/main.gcno'), ('tests', 'build/main.gcda'),
                           ('coverage-report', 'coverage.info'), ('coverage-report', 'coverage.xml'),
                           ('link', 'build/app'), ('tests', 'test-build/junit.xml'),
                           ('tests', 'test-build/Testing/Temporary/LastTest.log')]:
        artifact_id = role(executed, step, 'output', filename)
        body = parent.read_bytes(artifact_id)
        assert body == (workspace / filename).read_bytes() and body
        retained[filename] = {'artifact_id': artifact_id, 'step': step, **descriptor(body)}
    for filename in ('build/main.gcno', 'build/main.gcda'):
        consumed = role(executed, 'coverage-report', 'input', filename)
        assert descriptor(parent.read_bytes(consumed)) == {
            field: retained[filename][field] for field in ('sha256', 'size_bytes')}
        retained[filename]['report_input_artifact_id'] = consumed
    for adapter, filename in (('lcov', 'coverage.info'), ('cobertura', 'coverage.xml')):
        assert retained[filename]['artifact_id'] == selections[adapter]['report_artifact_id']
    return versions, retained


def assert_fact(fact, adapter, parent, selection, *, imported=False):
    assert fact['context_id'] == 'gcc-coverage-job' and fact['usability'] == 'usable'
    assert fact['origin'] == ('import' if imported else 'execution')
    assert fact['adapter']['name'] == adapter
    assert fact['report_artifact_id'] == selection['report_artifact_id']
    file, = fact['files']
    assert file['file'] == 'main.cpp'
    measurements = {row['kind']: row for row in file['measurements']}
    assert {kind: (row['covered'], row['total']) for kind, row in measurements.items()} == COUNTS[adapter]
    for kind, row in measurements.items():
        assert row['method'] == METHODS[adapter][kind]
        assert row['covered'] == sum(unit['covered'] for unit in row['units'])
        assert row['total'] == sum(unit['total'] for unit in row['units'])
    if imported:
        assert fact['receipt_id'] is None and not fact['proof_receipt_ids'] and not fact['test_evidence_ids']
        assert not fact['instrumentation'] and not fact['profiles'] and file['source_sha256'] is None
    else:
        assert fact['receipt_id'] == selection['receipt_id'] and fact['profiles'] == selection['profiles']
        assert fact['instrumentation'] == selection['instrumentation']
        assert fact['test_evidence_ids'] == selection['test_evidence_ids']
        assert set(fact['proof_receipt_ids']) == set(selection['proof_receipt_ids'])
        selected = next(row for row in parent.manifest['source']['files'] if row['path'] == 'main.cpp')
        assert file['source_sha256'] == selected['sha256']


def control(fact, kind, method, threshold=60):
    return {'id': kind, 'title': f'Selected {kind} coverage', 'kind': 'minimum_coverage',
            'weight': 1, 'required': True, 'depends_on': [],
            'parameters': {'fact_ids': [fact['id']], 'measurement_kind': kind, 'method': method,
                           'minimum': threshold, 'contexts': [fact['context_id']]}}


def policy(name, fact, controls):
    return {'version': '2.0.0', 'id': name, 'policy_version': '1.0.0', 'evaluator_profile': '1.1.0',
            'standards': [], 'scope': {'include': ['main.cpp'], 'exclude': []},
            'contexts': [fact['context_id']], 'gates': {'minimum_readiness': 100, 'minimum_completeness': 100},
            'controls': controls}


def policy_command(out, name, verb, selected, workspace, policy_path, expected):
    return external(out, f'{name}-{verb}', [CLI, verb, '--store', selected.path.parents[1],
                    '--workspace', workspace, '--run-id', selected.run_id,
                    '--manifest-sha256', selected.manifest_sha256, '--policy', policy_path], expected)


def typed_reports(out, name, target, fact, assessment=None):
    outputs = {}
    for fmt in ('json', 'html'):
        destination = out / f'{name}-report.{fmt}'
        _, result = external(out, f'{name}-report-{fmt}', [CLI, 'report', '--input', target.path.parents[1],
                             '--evidence', '--run-id', target.run_id, '--manifest-sha256', target.manifest_sha256,
                             '--format', fmt, '--output', destination], 0)
        body = destination.read_bytes()
        assert result['run_id'] == target.run_id and result['manifest_sha256'] == target.manifest_sha256
        assert result['bytes'] == len(body) and result['mode'] == 'snapshot_view'
        if fmt == 'json':
            view = json.loads(body)
            validate('snapshot_view', view)
            assert view['run']['id'] == target.run_id and view['run']['manifest_sha256'] == target.manifest_sha256
            row, = [item for item in view['facts'] if item['kind'] == 'coverage_facts']
            assert row['raw_json'].encode() == target.read_bytes(row['artifact_id'])
            assert sha(row['raw_json'].encode()) == row['sha256'] and json.loads(row['raw_json']) == fact
            if assessment is None:
                assert view['assessment'] is None
            else:
                assert json.loads(view['assessment']['raw_json']) == assessment
        else:
            text = html.unescape(body.decode())
            assert 'Recorded coverage measurements' in text and f"origin: {fact['origin']}" in text
            for row in fact['files'][0]['measurements']:
                assert row['method'] in text and f"{row['covered']} / {row['total']}" in text
            if assessment is None:
                assert 'Not assessed' in text
            else:
                assert all(row['reason'] in text for row in assessment['controls'])
        outputs[fmt] = descriptor(body)
    return outputs


def assess_one(out, name, selected, workspace, fact, kind, method, expected):
    document = policy(name, fact, [control(fact, kind, method)])
    validate_evaluation_policy(document)
    file = out / f'{name}-policy.json'
    write_json(file, document)
    store = RunStore.open_existing(selected.path.parents[1])
    outcomes = {}
    for verb in ('assess', 'check'):
        _, response = policy_command(out, name, verb, selected, workspace, file, expected)
        validate('workflow_result' if verb == 'assess' else 'check_result', response)
        selected_run = response['final_run'] if verb == 'assess' else response['run']
        result = store.open_run(selected_run['run_id'], manifest_sha256=selected_run['manifest_sha256'])
        result.verify()
        assessment = result.read_json(response['assessment_artifact_id'])
        row, = assessment['controls']
        assert row['id'] == kind and row['status'] == STATUSES[expected]
        assert assessment['gate'] == ('insufficient_evidence' if expected == 3 else STATUSES[expected])
        assert row['fact_ids'] == [fact['id']] and method in row['reason']
        if expected == 3:
            assert 'Missing, incompatible, zero or conflicting coverage units' in row['reason']
        else:
            counts = COUNTS[fact['adapter']['name']][kind]
            assert f'{counts[0]}/{counts[1]}' in row['reason']
        outcomes[verb] = {'exit': expected, 'assessment': assessment, 'result': pin(result)}
        if verb == 'assess':
            outcomes['reports'] = typed_reports(out, name, result, fact, assessment)
    for key in ('controls', 'gate', 'scores', 'weights'):
        assert outcomes['assess']['assessment'][key] == outcomes['check']['assessment'][key]
    return outcomes


def make_import(out, parent, workspace, adapter, selection):
    raw_id = selection['report_artifact_id']
    source_artifact = next(row for row in parent.manifest['artifacts'] if row['id'] == raw_id)
    store = RunStore(out / f'{adapter}-import-store')
    manifest = deepcopy(parent.manifest)
    manifest['stages'] = []
    manifest['limitations'] = [COVERAGE_LIMIT]
    with store.begin() as stage:
        stage.copy_artifact(raw_id, parent.path / source_artifact['path'], source_artifact['path'], source_artifact['media_type'])
        manifest.update(run_id=stage.run_id, artifacts=stage.artifacts)
        raw_only = stage.publish(manifest)
    result = coverage.normalize_imported_coverage(raw_only, report_artifact_id=raw_id, adapter=adapter,
                                                 context_id='gcc-coverage-job', source_root=str(workspace))
    assert_fact(result, adapter, raw_only, selection, imported=True)
    with store.begin() as stage:
        stage.copy_artifact(raw_id, raw_only.path / source_artifact['path'], source_artifact['path'], source_artifact['media_type'])
        stage.write_json('coverage/import.json', result, artifact_id='imported-coverage', contract='coverage_facts')
        manifest.update(run_id=stage.run_id, artifacts=stage.artifacts)
        imported = stage.publish(manifest)
    assert imported.read_bytes(raw_id) == parent.read_bytes(raw_id)
    assert imported.manifest['input_verification'] == 'unverified'
    assert set(read_documents(imported)) == {'run_manifest', 'coverage_facts'}
    return imported, result


def import_controls(out, parent, workspace, adapter, selection):
    imported, fact = make_import(out, parent, workspace, adapter, selection)
    name = f'{adapter}-import'
    document = policy(name, fact, [control(fact, kind, method) for kind, method in METHODS[adapter].items()])
    validate_evaluation_policy(document)
    file = out / f'{name}-policy.json'
    write_json(file, document)
    observed = evaluate_policy(document, read_documents(imported), generated_at=datetime.now(timezone.utc))
    write_json(out / f'{name}-pure-evaluation.json', observed)
    assert observed['gate'] == 'insufficient_evidence' and {row['status'] for row in observed['controls']} == {'unknown'}
    assert len(observed['controls']) == 3
    responses = {}
    for verb in ('assess', 'check'):
        _, response = policy_command(out, name, verb, imported, workspace, file, 3)
        assert response['assessment_artifact_id'] is None
        assert response['error']['code'] == 'UNVERIFIED_SOURCE', response
        responses[verb] = {'exit': 3, 'error': response['error']}
    return {'run': pin(imported), 'responses': responses, 'reports': typed_reports(out, name, imported, fact)}


def invalid_controls(out, selected, workspace, fact):
    names = {'decision-branch-method-zero': ('decision', METHODS['lcov']['branch']),
             'mcdc-branch-method-zero': ('mcdc', METHODS['lcov']['branch']),
             'branch-line-method-zero': ('branch', METHODS['lcov']['line'])}
    results = {}
    run_ids = {path.name for path in (selected.path.parents[1] / 'runs').iterdir()}
    for name, (kind, method) in names.items():
        file = out / f'{name}-policy.json'
        write_json(file, policy(name, fact, [control(fact, kind, method, 0)]))
        results[name] = {}
        for verb in ('assess', 'check'):
            receipt, diagnostic = policy_command(out, name, verb, selected, workspace, file, 2)
            if kind == 'branch':
                assert 'Unsupported coverage measurement method/kind' in diagnostic, diagnostic
            else:
                assert kind in diagnostic and ('not one of' in diagnostic or 'Unsupported' in diagnostic), diagnostic
            results[name][verb] = receipt
    assert {path.name for path in (selected.path.parents[1] / 'runs').iterdir()} == run_ids
    return results


def main():
    out = Path(sys.argv[1]).resolve(strict=True)
    assert Path.cwd() == out / 'outside' and Path.home() == Path('/home/agent')
    assert not list(Path.home().iterdir()) and shutil.which('cppulse') == str(CLI)
    for module in (cppulse, coverage):
        assert Path(module.__file__).resolve().is_relative_to(INSTALLED / 'cppulse')
    claim, tool_pins = candidate(), tool_scope()
    fixture = json.loads((LANE / 'fixture-freeze.json').read_bytes())
    driver = Path(fixture['driver'])
    assert digest(driver) == fixture['driver_sha256']
    helper = runpy.run_path(str(driver))
    tools = select_tools(helper, fixture)
    write_json(out / 'producer-request.json', {'driver': str(driver), 'driver_sha256': digest(driver),
               'tools': {name: {'path': path, 'sha256': digest(Path(path))} for name, path in tools.items()},
               'workspace_inputs': fixture['workspace_inputs']})
    parent, workspace = helper['prepare_collection'](out / 'producer', **tools)
    assert parent.manifest['status'] == 'completed' and parent.manifest['input_verification'] == 'verified'
    assert {row['path']: {field: row[field] for field in ('sha256', 'size_bytes')}
            for row in parent.manifest['source']['files']} == fixture['workspace_inputs']
    ensure_current_materials(parent, workspace)
    selections = {adapter: helper['roles'](parent, adapter) for adapter in METHODS}
    versions, raw = actual_raw(parent, workspace, selections)
    write_json(out / 'producer-material.json', {'run': pin(parent), 'versions': versions, 'raw_artifacts': raw})
    results, imports = {}, {}
    for adapter, selection in selections.items():
        store = out / f'{adapter}-execution-store'
        derived = coverage.persist_coverage(parent, workspace=workspace, store=store, **selection)
        derived = RunStore.open_existing(store).open_run(**pin(derived))
        assert all(row in derived.manifest['artifacts'] for row in parent.manifest['artifacts'])
        fact, = read_documents(derived)['coverage_facts']
        assert_fact(fact, adapter, parent, selection)
        write_json(out / f'{adapter}-execution-fact.json', fact)
        by_kind = {}
        for kind, method in METHODS[adapter].items():
            expected = 1 if kind == 'branch' else 3 if adapter == 'cobertura' and kind == 'function' else 0
            by_kind[kind] = assess_one(out, f'{adapter}-{kind}', derived, workspace, fact, kind, method, expected)
        if adapter == 'lcov':
            negatives = invalid_controls(out, derived, workspace, fact)
        results[adapter] = {'run': pin(derived), 'controls': by_kind}
        imports[adapter] = import_controls(out, parent, workspace, adapter, selection)
    ensure_current_materials(parent, workspace)
    versions_end, raw_end = actual_raw(parent, workspace, selections)
    assert raw_end == raw and versions_end == versions and candidate() == claim and tool_scope() == tool_pins
    write_json(out / 'qualification.json', {'criterion': 'FR-EVD-09', 'candidate': claim,
               'fixture': 'Tracked authored fixture executed with actual GCC/gcovr/CTest',
               'producer': pin(parent), 'versions': versions, 'provider_integrity': tool_pins,
               'raw_artifacts': raw, 'execution': results, 'imports': imports, 'invalid': negatives})
    print('FR-EVD-09 actual coverage, policy gates and origin controls recorded')


if __name__ == '__main__':
    main()
