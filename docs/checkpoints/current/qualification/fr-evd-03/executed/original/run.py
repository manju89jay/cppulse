"""Collect real bounded CTest evidence and check explicit no-false-pass controls."""

from copy import deepcopy
from importlib import import_module
import json
from pathlib import Path
import runpy
import shutil
import sys
import xml.etree.ElementTree as ET

import cppulse
from cppulse.contracts import validate, validate_evaluation_policy
from cppulse.identities import context_identity
from cppulse.run_store import RunStore
from cppulse.workflows import ensure_current_materials, read_documents


LANE = Path(__file__).resolve().parent
WORK = LANE.parents[1]
SOURCE = WORK / 'governance-qualification/checkout'
HELPER = runpy.run_path(str(WORK / 'current38-batch12/coverage-dimensions/run.py'))
INSTALLED = HELPER['INSTALLED']
CLI = HELPER['CLI']
CTEST = '/workspace/cppulse/.venv/bin/ctest'
CMAKE = '/workspace/cppulse/.venv/bin/cmake'
COMPILER = '/usr/bin/x86_64-linux-gnu-g++-14'
CONTEXT = 'native'
FIXTURES = json.loads((LANE / 'fixtures.json').read_bytes())
CHECK_STATUS = {0: 'passed', 1: 'failed', 3: 'unknown'}
GATE = {0: 'passed', 1: 'failed', 3: 'insufficient_evidence'}
AUTHORED = 'Finite synthetic source. The recorded runtime or imported origin governs the verification status.'


def write(path, value):
    HELPER['write_json'](path, value)


def pin(snapshot):
    return HELPER['pin'](snapshot)


def external(out, name, argv, expected):
    return HELPER['external'](out, name, argv, expected)[1]


def role(facts, step, direction, path):
    return HELPER['role'](facts, step, direction, path)


def opened(store, reference):
    selected = RunStore.open_existing(store).open_run(reference['run_id'], manifest_sha256=reference['manifest_sha256'])
    selected.verify()
    return selected


def base_request(name, files, contexts, plan, normalizers=()):
    return {'version': '2.0.0', 'id': name,
            'source': {'kind': 'application', 'files': files, 'inventory_complete': True, 'limitations': [AUTHORED]},
            'contexts': contexts, 'plan': plan, 'normalizers': list(normalizers)}


def native_request(name, workspace):
    expected = FIXTURES['native'][name]
    fixture = runpy.run_path(str(SOURCE / 'tests/test_collection.py'))['ctest_fixture']
    plan, source, contexts = fixture(workspace, fail_test=name == 'failure', no_tests=name == 'zero')
    selected = {'main.cpp': expected['body'], 'CMakeLists.txt': FIXTURES['cmake_common'] + (
        FIXTURES['cmake_test'] if expected['test'] else '')}
    cmake = workspace / 'CMakeLists.txt'
    main = workspace / 'main.cpp'
    assert cmake.read_text() == selected['CMakeLists.txt']
    if name == 'skipped':
        assert main.read_text() == FIXTURES['native']['clean']['body']
        selected['CMakeLists.txt'] += FIXTURES['cmake_skip']
        main.write_text(expected['body'])
        cmake.write_text(selected['CMakeLists.txt'])
    assert main.read_text() == selected['main.cpp']
    assert [row['path'] for row in source['files']] == sorted(selected)
    steps = {row['id']: row for row in plan['recipe']['steps']}
    assert steps['configure']['argv'][0] == CMAKE and steps['tests']['argv'][0] == CTEST
    # A fixed compiler keeps the fixture tied to the registered 14.2 runtime.
    steps['configure']['argv'].append('-DCMAKE_CXX_COMPILER=' + COMPILER)
    plan['recipe']['jobs'] = 1
    if name == 'show-only':
        steps['tests']['argv'] = [CTEST, '--show-only=json-v1']
    return base_request(name, sorted(selected), contexts, plan), selected


def imported_request(name, workspace):
    expected = FIXTURES['imports'][name]
    source = FIXTURES['import_source']
    (workspace / 'main.cpp').write_text(source)
    (workspace / 'payload.xml').write_bytes(expected['xml'].encode())
    shutil.copyfile(LANE / 'writer.py', workspace / 'writer.py')
    writer_python = '/workspace/cppulse/.venv/bin/python'
    argv = [writer_python, '-B', 'writer.py']
    context = context_identity({'id': CONTEXT, 'compiler': {'name': 'authored-import-fixture', 'version': '1'},
        'argv': argv, 'working_directory': str(workspace), 'language_standard': None, 'target': None,
        'provenance': 'inferred', 'dependencies': [], 'limitations': [AUTHORED, 'The writer copies authored input bytes.']})
    plan = {'version': '2.0.0', 'id': 'import-plan',
            'recipe': {'version': '2.0.0', 'id': 'import-recipe', 'jobs': 1, 'contexts': [CONTEXT],
                'steps': [{'id': 'writer', 'context_id': CONTEXT, 'argv': argv, 'cwd': '.', 'depends_on': [],
                           'inputs': ['writer.py', 'payload.xml'], 'outputs': ['report.xml'], 'timeout_seconds': 20}]},
            'bindings': [], 'limits': {'max_log_bytes': 1048576, 'max_artifact_bytes': 1048576,
                                        'max_metadata_bytes': 16777216, 'termination_grace_seconds': 1}}
    normalized = {'id': 'test-import', 'kind': 'test_import', 'normalizer_version': '1.0.0',
                  'report': {'step_id': 'writer', 'role': 'output', 'path': 'report.xml'},
                  'context_id': CONTEXT, 'scope_files': ['main.cpp'], 'adapter': 'generic-junit',
                  'producer': {'name': 'authored-fixture', 'version': '1'}}
    files = {'main.cpp': source, 'payload.xml': expected['xml'], 'writer.py': (LANE / 'writer.py').read_text()}
    return base_request(name, sorted(files), [context], plan, [normalized]), files


def select_records(run):
    docs = read_documents(run)
    facts = {record['receipt']['id']: record for record in docs['execution_facts']}
    records = [record for doc in docs['evidence'] for record in doc['records'] if record['kind'] == 'tests']
    record, = records
    return facts, record


def artifact(run, identifier):
    artifact = next(row for row in run.manifest['artifacts'] if row['id'] == identifier)
    assert HELPER['descriptor'](run.read_bytes(identifier)) == {k: artifact[k] for k in ('size_bytes', 'sha256')}
    return {'artifact_id': identifier, 'sha256': artifact['sha256'], 'size_bytes': artifact['size_bytes']}


def native_executed(out, name, selected, workspace, collect_run):
    expected = FIXTURES['native'][name]
    facts, record = select_records(selected)
    tests = facts['tests']
    receipt = tests['receipt']
    assert receipt['exit_code'] == expected['native_exit']
    assert receipt.get('tests') == expected['counts']
    assert receipt['status'] == ('failed' if name == 'failure' else 'passed')
    assert record['status'] == expected['status'] and record['usability'] == expected['usability'], record
    assert record['origin'] == 'execution' and record['receipt_id'] == 'tests' and record['context_id'] == CONTEXT
    assert record['producer']['name'] == 'ctest' and record['producer']['version'] == '3.31.6'
    assert b'ctest version 3.31.6' in selected.read_bytes(facts['version']['binding']['log_artifacts']['stdout'])
    assert len({facts[step]['executable_fact']['sha256'] for step in ('version', 'inventory', 'tests')}) == 1
    binary = role(facts, 'build', 'output', 'build/app')
    built_bytes = selected.read_bytes(binary)
    for step in ('inventory', 'tests'):
        assert selected.read_bytes(role(facts, step, 'input', 'build/app')) == built_bytes
    inventory_id = facts['inventory']['binding']['log_artifacts']['stdout']
    testcase_names = ['actual-case'] if expected['test'] else []
    inventory = json.loads(selected.read_bytes(inventory_id))
    assert [case['name'] for case in inventory['tests']] == testcase_names
    if name == 'show-only':
        assert tests['receipt']['argv'] == [CTEST, '--show-only=json-v1']
        assert not (workspace / 'build/junit.xml').exists() and not (workspace / 'build/Testing/Temporary/LastTest.log').exists()
        assert json.loads(selected.read_bytes(tests['binding']['log_artifacts']['stdout'])) == inventory
        assert tests['binding']['output_artifacts'] == [] and 'tests' not in receipt
        junit_output = last_test_output = None
    else:
        junit_id = role(facts, 'tests', 'output', 'build/junit.xml')
        log_id = role(facts, 'tests', 'output', 'build/Testing/Temporary/LastTest.log')
        junit_xml = selected.read_bytes(junit_id)
        log_body = selected.read_bytes(log_id)
        assert junit_xml == (workspace / 'build/junit.xml').read_bytes()
        assert log_body == (workspace / 'build/Testing/Temporary/LastTest.log').read_bytes()
        cases = list(ET.fromstring(junit_xml).iter('testcase'))
        assert [row.get('name') for row in cases] == testcase_names
        if name == 'skipped':
            assert cases[0].find('skipped') is not None and b'Test Passed.' in log_body
        if name == 'failure':
            assert cases[0].find('failure') is not None and b'Test Failed.' in log_body
        if name == 'clean':
            assert not list(cases[0].iter('failure')) and not list(cases[0].iter('skipped')) and b'Test Passed.' in log_body
        junit_output, last_test_output = artifact(selected, junit_id), artifact(selected, log_id)
    descriptor = {'store': str(selected.path.parents[1]), 'workspace': str(workspace), 'run': pin(selected),
                  'raw_run': {k: collect_run['raw_run'][k] for k in ('run_id', 'manifest_sha256')},
                  'test_evidence_id': record['id'], 'producer_version': record['producer']['version'],
                  'counts': receipt.get('tests'), 'native_exit': receipt['exit_code'], 'junit': junit_output,
                  'last_test': last_test_output, 'source_digest': selected.manifest['source']['digest'],
                  'context_id': CONTEXT, 'binary': artifact(selected, binary), 'inventory': artifact(selected, inventory_id)}
    write(out / 'producer.json', descriptor)
    return record


def imported_fact(out, name, selected, result):
    expected = FIXTURES['imports'][name]
    facts, record = select_records(selected)
    assert set(facts) == {'writer'} and facts['writer']['receipt']['exit_code'] == 0
    assert 'tests' not in facts['writer']['receipt'] and record['origin'] == 'import' and record['receipt_id'] is None
    assert record['status'] == 'error' and record['usability'] == expected['usability'], record
    assert record['test_counts'] is None and not record['test_cases'] and not record['scope']['tests']
    assert record['import_adapter'] == {'name': 'generic-junit', 'version': '1.0.0'}
    identifier = role(facts, 'writer', 'output', 'report.xml')
    assert selected.read_bytes(identifier) == expected['xml'].encode() and identifier in record['artifact_ids']
    normalizer, = result['normalizers']
    assert normalizer['status'] == 'completed' and normalizer['usability'] == expected['usability']
    write(out / 'import-artifact.json', artifact(selected, identifier))
    return record


def checks(out, name, selected, workspace, record, expected):
    policy = {'version': '2.0.0', 'id': name + '-tests', 'policy_version': '1.0.0', 'evaluator_profile': '1.0.0',
              'standards': [], 'scope': {'include': ['main.cpp'], 'exclude': []}, 'contexts': [CONTEXT],
              'gates': {'minimum_readiness': 100, 'minimum_completeness': 100},
              'controls': [{'id': 'tests', 'title': 'Required selected tests', 'kind': 'test_outcomes', 'required': True,
                            'weight': 1, 'depends_on': [], 'parameters': {'evidence_ids': [record['id']], 'contexts': [CONTEXT]}}]}
    validate_evaluation_policy(policy)
    policy_path = out / 'policy.json'
    write(policy_path, policy)
    store = selected.path.parents[1]
    controls = {}
    for verb in ('assess', 'check'):
        _, result = HELPER['policy_command'](out, name, verb, selected, workspace, policy_path, expected)
        assert result['error'] is None and result['assessment_artifact_id'], result
        current = opened(store, result['final_run'] if verb == 'assess' else result['run'])
        assessment = current.read_json(result['assessment_artifact_id'])
        row, = assessment['controls']
        assert row['status'] == CHECK_STATUS[expected] and assessment['gate'] == GATE[expected]
        assert row['evidence_ids'] == [record['id']]
        controls[verb] = {'exit': result['exit_code'], 'assessment': assessment, 'run': pin(current)}
        if verb == 'assess':
            assess_snapshot = current
    for key in ('controls', 'gate', 'scores', 'weights'):
        assert controls['assess']['assessment'][key] == controls['check']['assessment'][key]
    reports = {}
    for fmt in ('json', 'html'):
        destination = out / f'assessed.{fmt}'
        result = external(out, f'report-{fmt}', [CLI, 'report', '--input', store, '--evidence',
                          '--run-id', assess_snapshot.run_id, '--manifest-sha256', assess_snapshot.manifest_sha256,
                          '--format', fmt, '--output', destination], 0)
        assert result['run_id'] == assess_snapshot.run_id and result['manifest_sha256'] == assess_snapshot.manifest_sha256
        body = destination.read_bytes()
        if fmt == 'json':
            view = json.loads(body)
            validate('snapshot_view', view)
            assert json.loads(view['assessment']['raw_json']) == controls['assess']['assessment']
            report_facts = [row for fact in view['facts'] if fact['kind'] == 'evidence'
                            for row in json.loads(fact['raw_json'])['records'] if row['id'] == record['id']]
            assert report_facts == [record]
        else:
            origin = 'Execution-derived' if record['origin'] == 'execution' else 'Imported producer claim'
            assert origin.encode() in body and record['id'].encode() in body
        reports[fmt] = HELPER['descriptor'](body)
    return {'controls': controls, 'reports': reports}


def scenario(out, name):
    native = name in FIXTURES['native']
    expected = FIXTURES['native' if native else 'imports'][name]
    workspace = out / 'workspace'
    workspace.mkdir()
    request, files = (native_request if native else imported_request)(name, workspace)
    validate('collection_request', request)
    path = out / 'collection-request.json'
    write(path, request)
    store = out / 'store'
    result = external(out, 'collect', [CLI, 'collect', '--workspace', workspace, '--store', store, '--request', path], expected['collect_exit'])
    assert result['error'] is None and result['status'] == ('completed' if expected['collect_exit'] == 0 else 'partial')
    selected = opened(store, result['final_run'])
    assert selected.manifest['input_verification'] == 'verified'
    ensure_current_materials(selected, workspace)
    record = native_executed(out, name, selected, workspace, result) if native else imported_fact(out, name, selected, result)
    write(out / 'evidence-record.json', record)
    outcome = checks(out, name, selected, workspace, record, expected['policy_exit'])
    ensure_current_materials(selected, workspace)
    for filename, source in files.items():
        assert (workspace / filename).read_bytes() == source.encode()
    write(out / 'phase-result.json', {'name': name, 'collection_exit': result['exit_code'],
                                      'selected_run': pin(selected), **outcome})


def reservation(out, name):
    candidate = HELPER['candidate']()
    assert Path(cppulse.__file__).resolve().is_relative_to(INSTALLED / 'cppulse')
    for module in ('collection', 'adapters.test_results', 'policy', 'workflows'):
        loaded = import_module('cppulse.' + module)
        assert Path(loaded.__file__).resolve().is_relative_to(INSTALLED / 'cppulse')
    assert shutil.which('cppulse') == str(CLI) and Path.home() == Path('/home/agent')
    if name == 'before':
        assert not list(Path.home().iterdir())
    write(out / f'candidate-{name}.json', candidate)


def summarize(out):
    candidate = HELPER['candidate']()
    producers = {}
    for name in FIXTURES['native']:
        path = out / name / 'producer.json'
        if path.is_file():
            retained = json.loads(path.read_bytes())
            opened(Path(retained['store']), retained['run'])
            producers[name] = retained
    write(out / 'producer-descriptor.json', {'criterion': 'FR-EVD-03', 'candidate': candidate, 'producers': producers})
    expected = {*FIXTURES['native'], *FIXTURES['imports']}
    actual = {name: int((out / name / 'phase.exit').read_text()) for name in sorted(expected)}
    assert set(producers) == FIXTURES['native'].keys() and set(actual.values()) == {0}, actual
    write(out / 'qualification.json', {'criterion': 'FR-EVD-03', 'candidate': candidate,
          'producers': producers, 'phase_exits': actual, 'scenarios': {name: json.loads((out / name / 'phase-result.json').read_bytes()) for name in actual}})


if __name__ == '__main__':
    name, output = sys.argv[1:]
    out = Path(output).resolve(strict=True)
    if name in ('before', 'after'):
        reservation(out, name)
    elif name == 'summarize':
        summarize(out)
    else:
        scenario(out, name)
