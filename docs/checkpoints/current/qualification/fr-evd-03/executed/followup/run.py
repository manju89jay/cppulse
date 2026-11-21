"""Retain the original show-only result and verify authored import-only negatives."""

from datetime import datetime, timezone
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

import cppulse
from cppulse.contracts import validate, validate_evaluation_policy
from cppulse.identities import context_identity, digest_json, snapshot_inputs
from cppulse.policy import evaluate_policy
from cppulse.run_store import RunStore
from cppulse.test_import import normalize_test_import
from cppulse.workflows import ensure_current_materials, read_documents


LANE = Path(__file__).resolve().parent
BASE = LANE.parent
OLD = BASE / 'results/no-false-verification'
ORIGIN = BASE / 'no-false-verification'
ORIGINAL = runpy.run_path(str(ORIGIN / 'run.py'))
HELPER = ORIGINAL['HELPER']
FIXTURES = ORIGINAL['FIXTURES']
INSTALLED = ORIGINAL['INSTALLED']
CLI = ORIGINAL['CLI']
CONTEXT = ORIGINAL['CONTEXT']
PYTHON = '/workspace/cppulse/.venv/bin/python'


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    ORIGINAL['write'](path, value)


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        assert not path.is_symlink() and (path.is_file() or path.is_dir()), path
        if path.is_file():
            result[path.relative_to(root).as_posix()] = HELPER['digest'](path)
    return result


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def preflight(out, phase):
    assert Path(cppulse.__file__).resolve().is_relative_to(INSTALLED / 'cppulse')
    assert shutil.which('cppulse') == str(CLI) and Path.home() == Path('/home/agent')
    if phase == 'before':
        assert not list(Path.home().iterdir())
    frozen = read(LANE / 'sealed-original.json')
    assert inventory(OLD) == frozen['files']
    candidate = HELPER['candidate']()
    prior = read(OLD / 'producer-descriptor.json')
    assert prior['candidate'] == candidate
    assert set(prior['producers']) == {'clean', 'failure', 'zero', 'skipped'}
    for name, retained in prior['producers'].items():
        assert (OLD / name / 'phase.exit').read_text().strip() == '0'
        selected = ORIGINAL['opened'](Path(retained['store']), retained['run'])
        ensure_current_materials(selected, Path(retained['workspace']))
    for name in ('show-only', *FIXTURES['imports']):
        assert (OLD / name / 'phase.exit').read_text().strip() == '1'
    write(out / f'custody-{phase}.json', {'candidate': candidate, 'original_files': len(frozen['files']),
          'original_inventory_sha256': HELPER['digest'](LANE / 'sealed-original.json'),
          'prior_native_producers': prior['producers'], 'original_show_only': frozen['original_show_only']})


def show_only(out):
    case = OLD / 'show-only'
    workspace = case / 'workspace'
    original_store = case / 'store'
    collected = read(case / 'collect.stdout')
    assert read(case / 'collect.command.json')['exit'] == collected['exit_code'] == 3
    assert collected['status'] == 'partial' and collected['error'] is None
    original = ORIGINAL['opened'](original_store, collected['final_run'])
    assert original.manifest['status'] == 'partial' and original.manifest['input_verification'] == 'verified'
    ensure_current_materials(original, workspace)
    facts, record = ORIGINAL['select_records'](original)
    actual = facts['tests']
    receipt = actual['receipt']
    assert receipt['argv'] == [ORIGINAL['CTEST'], '--show-only=json-v1']
    assert receipt['exit_code'] == 0 and receipt['status'] == 'passed' and 'tests' not in receipt
    assert record['status'] == 'error' and record['usability'] == 'missing' and not record['scope'].get('tests', [])
    assert record['id'] == 'native-tests' and record['receipt_id'] == 'tests'
    assert record['producer']['name'] == 'ctest' and record['producer']['version'] == '3.31.6'
    assert actual['material_status'] == 'missing'
    assert not (workspace / 'build/junit.xml').exists()
    assert [item['path'] for item in actual['binding']['output_artifacts']] == ['build/Testing/Temporary/LastTest.log']
    last_test = ORIGINAL['role'](facts, 'tests', 'output', 'build/Testing/Temporary/LastTest.log')
    observed_log = original.read_bytes(last_test)
    assert observed_log == (workspace / 'build/Testing/Temporary/LastTest.log').read_bytes()
    start, separator, end = observed_log.decode().splitlines()
    assert start.startswith('Start testing: ') and set(separator) == {'-'} and end.startswith('End testing: ')
    inventory_id = facts['inventory']['binding']['log_artifacts']['stdout']
    listing = json.loads(original.read_bytes(actual['binding']['log_artifacts']['stdout']))
    assert listing == json.loads(original.read_bytes(inventory_id))
    assert [row['name'] for row in listing['tests']] == ['actual-case']
    binary = ORIGINAL['role'](facts, 'build', 'output', 'build/app')
    assert original.read_bytes(binary) == original.read_bytes(ORIGINAL['role'](facts, 'tests', 'input', 'build/app'))
    copied = out / 'show-only-private-store'
    shutil.copytree(original_store, copied)
    assert inventory(copied) == inventory(original_store)
    selected = ORIGINAL['opened'](copied, collected['final_run'])
    assert selected.read_manifest_bytes() == original.read_manifest_bytes()
    output = ORIGINAL['checks'](out, 'show-only', selected, workspace, record, 3)
    ensure_current_materials(original, workspace)
    write(out / 'phase-result.json', {'original_run': ORIGINAL['pin'](original), 'private_store': str(copied),
          'collection_exit': 3, 'native_exit': 0, 'junit': None, 'counts': None, 'named_test_events': 0,
          'last_test': ORIGINAL['artifact'](original, last_test), 'inventory': ORIGINAL['artifact'](original, inventory_id),
          'binary': ORIGINAL['artifact'](original, binary), **output})


def archive(out, name, expected):
    workspace = out / 'workspace'
    workspace.mkdir()
    (workspace / 'main.cpp').write_text(FIXTURES['import_source'])
    (workspace / 'payload.xml').write_bytes(expected['xml'].encode())
    shutil.copyfile(ORIGIN / 'writer.py', workspace / 'writer.py')
    started = now()
    argv = [PYTHON, '-B', 'writer.py']
    result = subprocess.run(argv, cwd=workspace, capture_output=True, timeout=20, check=False)
    finished = now()
    (out / 'writer.stdout').write_bytes(result.stdout)
    (out / 'writer.stderr').write_bytes(result.stderr)
    write(out / 'writer.command.json', {'argv': argv, 'cwd': str(workspace), 'started_at': started,
          'finished_at': finished, 'native_exit': result.returncode, 'purpose': 'copy authored XML only'})
    assert result.returncode == 0 and not result.stdout and not result.stderr
    xml = workspace / 'report.xml'
    assert xml.read_bytes() == expected['xml'].encode()
    source = snapshot_inputs(workspace, ['main.cpp', 'payload.xml', 'writer.py'], inventory_complete=True)
    context = context_identity({'id': CONTEXT, 'compiler': {'name': 'authored-import-fixture', 'version': '1'},
        'argv': argv, 'working_directory': str(workspace), 'language_standard': None, 'target': None,
        'provenance': 'inferred', 'dependencies': [], 'limitations': ['No test producer was run.']})
    store = RunStore(out / 'import-store')
    manifest = {'version': '2.0.0', 'status': 'completed', 'source': source, 'contexts': [context],
                'stages': [], 'started_at': started, 'finished_at': finished,
                'config_digest': digest_json({'fixture': name}), 'versions': {'cppulse': cppulse.__version__},
                'limitations': ['Authored generic XML import; neither source freshness nor test execution is asserted.']}
    with store.begin() as stage:
        stage.copy_artifact('raw-report', xml, 'reports/authored.xml', 'application/xml')
        raw = stage.publish({**manifest, 'run_id': stage.run_id, 'artifacts': stage.artifacts})
    document = normalize_test_import(raw, report_artifact_id='raw-report', context_id=CONTEXT,
        scope_files=['main.cpp'], adapter='generic-junit', producer={'name': 'authored-fixture', 'version': '1'})
    fact, = document['records']
    assert fact['status'] == 'error' and fact['usability'] == expected['usability'], fact
    assert fact['origin'] == 'import' and fact['receipt_id'] is None and fact['test_counts'] is None
    assert not fact['test_cases'] and not fact['scope']['tests']
    assert fact['artifact_ids'] == ['raw-report']
    with store.begin() as stage:
        stage.copy_artifact('raw-report', raw.path / 'reports/authored.xml', 'reports/authored.xml', 'application/xml')
        stage.write_json('tests/import.json', document, artifact_id='imported-evidence', contract='evidence')
        selected = stage.publish({**manifest, 'run_id': stage.run_id, 'artifacts': stage.artifacts, 'status': 'partial'})
    assert selected.manifest['input_verification'] == 'unverified'
    assert set(read_documents(selected)) == {'run_manifest', 'evidence'}
    assert selected.read_bytes('raw-report') == expected['xml'].encode()
    return workspace, selected, fact


def imported(out, name):
    expected = FIXTURES['imports'][name]
    workspace, selected, fact = archive(out, name, expected)
    policy = {'version': '2.0.0', 'id': name + '-tests', 'policy_version': '1.0.0', 'evaluator_profile': '1.0.0',
              'standards': [], 'scope': {'include': ['main.cpp'], 'exclude': []}, 'contexts': [CONTEXT],
              'gates': {'minimum_readiness': 100, 'minimum_completeness': 100},
              'controls': [{'id': 'tests', 'title': 'Required selected tests', 'kind': 'test_outcomes', 'required': True,
                            'weight': 1, 'depends_on': [], 'parameters': {'evidence_ids': [fact['id']], 'contexts': [CONTEXT]}}]}
    validate_evaluation_policy(policy)
    causal = evaluate_policy(policy, read_documents(selected), generated_at=now())
    assert causal['gate'] == 'insufficient_evidence'
    control, = causal['controls']
    assert control['status'] == 'unknown' and control['evidence_ids'] == [fact['id']]
    write(out / 'pure-evaluation.json', causal)
    policy_path = out / 'policy.json'
    write(policy_path, policy)
    commands = {}
    for verb in ('assess', 'check'):
        _, result = HELPER['policy_command'](out, name, verb, selected, workspace, policy_path, 3)
        assert result['error']['code'] == 'UNVERIFIED_SOURCE' and result['assessment_artifact_id'] is None
        commands[verb] = {'exit': result['exit_code'], 'error': result['error']}
    reports = {}
    for fmt in ('json', 'html'):
        destination = out / f'historical.{fmt}'
        result = ORIGINAL['external'](out, f'report-{fmt}', [CLI, 'report', '--input', selected.path.parents[1], '--evidence',
            '--run-id', selected.run_id, '--manifest-sha256', selected.manifest_sha256, '--format', fmt, '--output', destination], 0)
        assert result['run_id'] == selected.run_id and result['manifest_sha256'] == selected.manifest_sha256
        body = destination.read_bytes()
        if fmt == 'json':
            view = json.loads(body)
            validate('snapshot_view', view)
            typed, = view['facts']
            assert view['assessment'] is None and typed['kind'] == 'evidence'
            assert json.loads(typed['raw_json'])['records'] == [fact]
        else:
            assert b'Imported producer claim' in body and b'Not assessed' in body
        reports[fmt] = HELPER['descriptor'](body)
    selected.verify()
    write(out / 'phase-result.json', {'run': ORIGINAL['pin'](selected), 'fact': fact, 'commands': commands,
          'reports': reports, 'raw_report': ORIGINAL['artifact'](selected, 'raw-report')})


if __name__ == '__main__':
    phase, out_arg = sys.argv[1:]
    out = Path(out_arg).resolve(strict=True)
    if phase in ('before', 'after'):
        preflight(out, phase)
    elif phase == 'show-only':
        show_only(out)
    else:
        imported(out, phase)
