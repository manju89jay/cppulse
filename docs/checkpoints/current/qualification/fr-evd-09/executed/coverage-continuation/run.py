"""Consume the sealed B12 producer and preserve exact structured CLI refusals."""

import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

import cppulse
from cppulse import coverage
from cppulse.contracts import validate
from cppulse.run_store import RunStore
from cppulse.workflows import ensure_current_materials, read_documents


LANE = Path(__file__).resolve().parent
BASE = LANE.parent
OLD = BASE / 'results/coverage-dimensions'
ORIGINAL = BASE / 'coverage-dimensions'
OLD_CODE = runpy.run_path(str(ORIGINAL / 'run.py'))
CLI = OLD_CODE['CLI']
INSTALLED = OLD_CODE['INSTALLED']
WORKSPACE = OLD / 'producer/workspace'
RAW_STORE = OLD / 'producer/store'
LCOV_STORE = OLD / 'lcov-execution-store'
POLICY_NODE = 'test_genuine_retained_lcov_public_assess_check_report_and_deviation'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def record(path, value):
    OLD_CODE['write_json'](path, value)


def pin(snapshot):
    return OLD_CODE['pin'](snapshot)


def files(root):
    entries = {}
    for path in sorted(root.rglob('*')):
        assert not path.is_symlink() and (path.is_file() or path.is_dir()), path
        if path.is_file():
            entries[path.relative_to(root).as_posix()] = digest(path)
    return entries


def producer():
    retained = read(OLD / 'producer-material.json')
    root = RunStore.open_existing(RAW_STORE).open_run(**retained['run'])
    assert root.manifest['status'] == 'completed' and root.manifest['input_verification'] == 'verified'
    ensure_current_materials(root, WORKSPACE)
    fixture = read(ORIGINAL / 'fixture-freeze.json')
    driver = Path(fixture['driver'])
    assert digest(driver) == fixture['driver_sha256']
    assert {row['path']: {key: row[key] for key in ('sha256', 'size_bytes')}
            for row in root.manifest['source']['files']} == fixture['workspace_inputs']
    helper = runpy.run_path(str(driver))
    selections = {adapter: helper['roles'](root, adapter) for adapter in OLD_CODE['METHODS']}
    versions, raw = OLD_CODE['actual_raw'](root, WORKSPACE, selections)
    assert versions == retained['versions'] and raw == retained['raw_artifacts']
    return root, selections, retained


def custody():
    bound = read(LANE / 'sealed-inputs.json')
    assert files(BASE / 'results') == bound['results_files']
    root, _, retained = producer()
    assert pin(root) == bound['original_producer']
    candidate = OLD_CODE['candidate']()
    initial = read(OLD / 'decision-branch-method-zero-assess.stdout')
    assert initial['status'] == 'invalid' and initial['exit_code'] == 2
    assert initial['error'] == {'code': 'INVALID_CONTRACT',
                                'path': '/controls/0/parameters/measurement_kind',
                                'message': "'decision' is not one of ['line', 'branch', 'function']"}
    assert not (OLD / 'decision-branch-method-zero-assess.stderr').read_bytes()
    return {'historical_closed_input_sha256': digest(LANE / 'sealed-inputs.json'),
            'historical_regular_file_count': len(bound['results_files']),
            'original_producer': retained, 'candidate': candidate,
            'prior_structured_exit': initial['exit_code'], 'prior_structured_error': initial['error']}


def derive(out, root, selection, adapter):
    store = out / 'execution-store'
    child = coverage.persist_coverage(root, workspace=WORKSPACE, store=store, **selection)
    child = RunStore.open_existing(store).open_run(**pin(child))
    assert all(row in child.manifest['artifacts'] for row in root.manifest['artifacts'])
    fact, = read_documents(child)['coverage_facts']
    OLD_CODE['assert_fact'](fact, adapter, root, selection)
    record(out / 'fact.json', fact)
    return child, fact


def execution(out, adapter):
    root, selections, _ = producer()
    fresh, fact = derive(out, root, selections[adapter], adapter)
    cases = {}
    for kind, method in OLD_CODE['METHODS'][adapter].items():
        expected = 1 if kind == 'branch' else 3 if adapter == 'cobertura' and kind == 'function' else 0
        cases[kind] = OLD_CODE['assess_one'](out, f'{adapter}-{kind}', fresh, WORKSPACE, fact, kind, method, expected)
    record(out / 'phase-result.json', {'adapter': adapter, 'run': pin(fresh), 'cases': cases})


def imported(out, adapter):
    root, selections, _ = producer()
    result = OLD_CODE['import_controls'](out, root, WORKSPACE, adapter, selections[adapter])
    record(out / 'phase-result.json', {'adapter': adapter, **result})


def rejected(out, selected, name, verb, policy_path, code, path, reason):
    store = selected.path.parents[1]
    argv = [str(value) for value in (CLI, verb, '--store', store, '--workspace', WORKSPACE,
            '--run-id', selected.run_id, '--manifest-sha256', selected.manifest_sha256,
            '--policy', policy_path)]
    cwd = out / 'outside'
    result = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=90, check=False)
    stem = f'{name}-{verb}'
    (out / f'{stem}.stdout').write_bytes(result.stdout)
    (out / f'{stem}.stderr').write_bytes(result.stderr)
    receipt = {'argv': argv, 'cwd': str(cwd), 'exit': result.returncode}
    record(out / f'{stem}.command.json', receipt)
    assert result.returncode == 2 and not result.stderr, (stem, result.returncode, result.stdout, result.stderr)
    response = json.loads(result.stdout)
    validate('workflow_result' if verb == 'assess' else 'check_result', response)
    assert response['status'] == 'invalid' and response['exit_code'] == 2
    assert response['error'] == {'code': code, 'path': path, 'message': reason} and response['reason'] == reason
    selected_run = response['raw_run'] if verb == 'assess' else response['run']
    assert selected_run['run_id'] == selected.run_id and selected_run['manifest_sha256'] == selected.manifest_sha256
    assert response['assessment_artifact_id'] is None and response['facts_base_run'] is None
    if verb == 'assess':
        assert response['final_run'] is None and response['policy_gate'] is None
    else:
        assert response['policy_sha256'] is None
    return {**receipt, 'structured_response': response}


def invalid(out):
    root, selections, _ = producer()
    selected, fact = derive(out, root, selections['lcov'], 'lcov')
    controls = OLD_CODE['control']
    policy = OLD_CODE['policy']
    method = OLD_CODE['METHODS']['lcov']
    names = {'decision-branch-method-zero': ('decision', method['branch']),
             'mcdc-branch-method-zero': ('mcdc', method['branch']),
             'branch-line-method-zero': ('branch', method['line'])}
    before = files(selected.path.parents[1])
    outcomes = {}
    for name, (kind, method_id) in names.items():
        policy_path = out / f'{name}-policy.json'
        record(policy_path, policy(name, fact, [controls(fact, kind, method_id, 0)]))
        if kind == 'branch':
            code, field, reason = 'UNSUPPORTED_VERSION', 'method', 'Unsupported coverage measurement method/kind'
        else:
            code, field, reason = 'INVALID_CONTRACT', 'measurement_kind', f"{kind!r} is not one of ['line', 'branch', 'function']"
        outcomes[name] = {verb: rejected(out, selected, name, verb, policy_path,
                          code, f'/controls/0/parameters/{field}', reason) for verb in ('assess', 'check')}
    assert before == files(selected.path.parents[1])
    record(out / 'phase-result.json', outcomes)


def prepare_m5(out):
    from shutil import copytree

    previously = read(Path('/workspace/work/current38-policy-m5/results/receipt.json'))
    assert previously['pytest_exit'] == 0 and previously['case_count'] == 283 and not previously['nonpassing']
    assert previously['junit_sha256'] == digest(Path('/workspace/work/current38-policy-m5/results/results.xml'))
    origin = read(OLD / 'lcov-line-assess.stdout')['raw_run']
    expected = {'run_id': origin['run_id'], 'manifest_sha256': origin['manifest_sha256']}
    old = RunStore.open_existing(LCOV_STORE).open_run(**expected)
    ensure_current_materials(old, WORKSPACE)
    old_fact, = read_documents(old)['coverage_facts']
    assert old_fact == read(OLD / 'lcov-execution-fact.json') and old_fact['origin'] == 'execution'
    copied_store = out / 'lcov-private-store'
    copytree(LCOV_STORE, copied_store)
    assert files(copied_store) == files(LCOV_STORE)
    copied = RunStore.open_existing(copied_store).open_run(**expected)
    assert copied.read_manifest_bytes() == old.read_manifest_bytes()
    ensure_current_materials(copied, WORKSPACE)
    record(out / 'original-store-inventory.json', files(LCOV_STORE))
    record(out / 'policy115-inputs.json', {**expected, 'workspace': str(WORKSPACE),
               'store': str(copied_store), 'console': str(CLI)})


def finish_m5(out):
    import xml.etree.ElementTree as ET

    spec = read(out / 'policy115-inputs.json')
    result_path, = [path for path in (out / 'pytest').glob('*/genuine-policy115-result.json')
                    if not path.parent.is_symlink()]
    result = read(result_path)
    completed = ET.fromstring((out / 'genuine-policy115.xml').read_bytes())
    suite, = list(completed)
    assert suite.get('tests') == '1' and all(suite.get(key) == '0' for key in ('errors', 'failures', 'skipped'))
    case, = suite.findall('testcase')
    assert case.get('name') == POLICY_NODE
    assert result['status'] == 'passed' and result['original_run_id'] == spec['run_id']
    assert result['original_manifest_sha256'] == spec['manifest_sha256']
    assert result['literal_measurements'] == {'line': [5, 8], 'branch': [1, 2], 'function': [2, 3]}
    readonly = RunStore.open_existing(LCOV_STORE).open_run(run_id=spec['run_id'], manifest_sha256=spec['manifest_sha256'])
    ensure_current_materials(readonly, WORKSPACE)
    assert read(out / 'original-store-inventory.json') == files(LCOV_STORE)
    record(out / 'phase-result.json', {'genuine_consumer': result, 'junit_sha256': digest(out / 'genuine-policy115.xml'),
              'unchanged_pure_283_junit_sha256': digest(Path('/workspace/work/current38-policy-m5/results/results.xml'))})


def main():
    command, out_arg = sys.argv[1:]
    out = Path(out_arg).resolve(strict=True)
    assert Path.home() == Path('/home/agent') and Path(cppulse.__file__).resolve().is_relative_to(INSTALLED / 'cppulse')
    assert shutil.which('cppulse') == str(CLI)
    if command in ('before', 'after'):
        if command == 'before':
            assert not list(Path.home().iterdir())
        record(out / f'custody-{command}.json', custody())
    elif command in ('lcov', 'cobertura'):
        execution(out, command)
    elif command in ('import-lcov', 'import-cobertura'):
        imported(out, command.removeprefix('import-'))
    elif command == 'invalid':
        invalid(out)
    elif command == 'm5-prepare':
        prepare_m5(out)
    elif command == 'm5-finish':
        finish_m5(out)
    else:
        raise ValueError(command)


if __name__ == '__main__':
    main()
