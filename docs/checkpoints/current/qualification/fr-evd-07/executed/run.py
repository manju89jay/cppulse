"""Collect and report the finite FR-EVD-07 template and standalone-header checks."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import cppulse
from cppulse import consumer
from cppulse.contracts import validate
from cppulse.identities import context_identity
from cppulse.run_store import RunStore
from cppulse.workflows import ensure_current_materials, read_documents


GATES = Path('/workspace/work/git-scope-qualification/gates')
INSTALLED = GATES / 'candidate/installed'
INPUT = Path(__file__).parent / 'input'
CLI = INSTALLED / 'bin/cppulse'
CANDIDATE_TREE = 'da3f8f074ddbf5a89a9fd6d673f2b39b23b37bbe'
WHEEL_SHA = 'db15edf7a6821442ea9b5321ffd3c9ca4d198e704c103cb1f6f044300c034700'
CONTEXT = 'selected-gcc-header'
HEADER = 'package/demo.hpp'
LOGICAL_HEADER = 'include/demo.hpp'
INSTANTIATION = 'selected<int>/SELECTED_MACRO=7'
LIMIT = 'Finite selected int workload with SELECTED_MACRO=7. Other template types and macro values were not exercised.'
NAMED_TEST = 'declared-template-checks'
MISSING_TEST = 'nonexistent-required-test'
EXPECTED_CTEST = {'selected-int-macro7', 'standalone-header'}
FLAGS = ['-std=c++17', '-O0', '-g0', '-Wall', '-Wextra', '-Werror', '-v', '-Ipackage', '-DSELECTED_MACRO=7']


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def sha(body):
    return hashlib.sha256(body).hexdigest()


def pin(snapshot):
    return {'run_id': snapshot.run_id, 'manifest_sha256': snapshot.manifest_sha256}


def installed_candidate():
    test_freeze, manifest = GATES / 'test-freeze.json', GATES / 'candidate/artifact.json'
    frozen_bytes, manifest_bytes = test_freeze.read_bytes(), manifest.read_bytes()
    frozen, artifact = json.loads(frozen_bytes), json.loads(manifest_bytes)
    for record in (frozen, artifact):
        assert record['candidate_tree'] == CANDIDATE_TREE and record['wheel_sha256'] == WHEEL_SHA
    assert frozen['candidate_manifest'] == str(manifest)
    assert frozen['candidate_manifest_sha256'] == sha(manifest_bytes)
    assert artifact['installed'] == str(INSTALLED) and artifact['console'] == str(CLI)
    console = CLI.read_bytes()
    assert console.startswith(b'#!/workspace/verification-python-venv/bin/python\n')
    assert sha(console) == artifact['console_sha256']
    assert sha(Path(artifact['wheel']).read_bytes()) == WHEEL_SHA
    return {'tree': CANDIDATE_TREE, 'wheel_sha256': WHEEL_SHA,
            'test_freeze_sha256': sha(frozen_bytes), 'candidate_manifest_sha256': sha(manifest_bytes),
            'console_sha256': sha(console)}


def selected_tool(name):
    installed_tool = shutil.which(name)
    assert installed_tool is not None, name
    return str(Path(installed_tool).resolve(strict=True))


def external(out, name, argv, *, timeout=60):
    command = [str(arg) for arg in argv]
    cwd = out / 'outside'
    result = subprocess.run(command, cwd=cwd, capture_output=True, timeout=timeout, check=False)
    (out / f'{name}.stdout').write_bytes(result.stdout)
    (out / f'{name}.stderr').write_bytes(result.stderr)
    write_json(out / f'{name}.command.json', {'argv': command, 'cwd': str(cwd), 'exit': result.returncode})
    assert result.returncode == 0, (name, result.returncode, result.stdout, result.stderr)
    return json.loads(result.stdout)


def step(identifier, argv, inputs=(), outputs=(), depends=(), *, cwd='.'):
    return {'id': identifier, 'context_id': CONTEXT, 'argv': argv, 'cwd': cwd,
            'inputs': list(inputs), 'outputs': list(outputs), 'depends_on': list(depends),
            'timeout_seconds': 30}


def compile_step(compiler, identifier, source, binary):
    depfile = f'build/{identifier}.d'
    link_map = f'build/{identifier}.map'
    return step(identifier,
                [compiler, *FLAGS, '-MMD', '-MF', depfile, source,
                 f'-Wl,-v,-Map,{link_map}', '-o', binary],
                [source, HEADER], [binary, depfile, link_map], ['configuration', 'target'])


def request_document(workspace):
    compiler, cmake, ctest = (selected_tool(tool) for tool in ('g++', 'cmake', 'ctest'))
    context = context_identity({
        'id': CONTEXT,
        'compiler': {'name': 'GNU', 'version': '14.2.0', 'sha256': sha(Path(compiler).read_bytes())},
        'argv': [compiler, *FLAGS], 'working_directory': str(workspace),
        'language_standard': 'c++17', 'target': 'x86_64-linux-gnu',
        'provenance': 'inferred', 'dependencies': [], 'limitations': [LIMIT],
    })
    binaries = ['build/selected-consumer', 'build/standalone-header']
    ctest_inputs = [*binaries, 'build/CTestTestfile.cmake']
    steps = [
        step('configuration', [compiler, *FLAGS, '-dM', '-E', '-x', 'c++', 'probe.cpp'], ['probe.cpp']),
        step('target', [compiler, '-dumpmachine']),
        compile_step(compiler, 'consumer', 'selected.cpp', binaries[0]),
        compile_step(compiler, 'selfcontained', 'standalone.cpp', binaries[1]),
        step('configure-tests', [cmake, '-S', '.', '-B', 'build'], ['CMakeLists.txt'],
             ['build/CTestTestfile.cmake', 'build/CMakeCache.txt']),
        step('ctest-version', [ctest, '--version']),
        step('inventory', [ctest, '--show-only=json-v1'], ctest_inputs,
             depends=['consumer', 'selfcontained', 'configure-tests'], cwd='build'),
        step('tests', [ctest, '--output-on-failure', '--output-junit', 'junit.xml'], ctest_inputs,
             ['build/junit.xml', 'build/Testing/Temporary/LastTest.log'],
             ['ctest-version', 'inventory'], cwd='build'),
    ]
    binding = {'id': NAMED_TEST, 'kind': 'tests', 'step_id': 'tests',
               'scope_files': [HEADER, 'selected.cpp', 'standalone.cpp'],
               'exercised_inputs': binaries, 'report_path': 'build/junit.xml',
               'adapter': 'ctest-junit', 'adapter_version': '1.0.0',
               'inventory_step_id': 'inventory', 'producer_version_step_id': 'ctest-version',
               'execution_log_path': 'build/Testing/Temporary/LastTest.log'}
    request = {
        'version': '2.0.0', 'id': 'fresh-selected-header',
        'source': {'kind': 'header-only', 'files': ['CMakeLists.txt', HEADER, 'selected.cpp', 'standalone.cpp', 'probe.cpp'],
                   'inventory_complete': True, 'limitations': [LIMIT]},
        'contexts': [context],
        'plan': {
            'version': '2.0.0', 'id': 'selected-header-plan',
            'recipe': {'version': '2.0.0', 'id': 'selected-header-recipe', 'jobs': 1,
                       'contexts': [CONTEXT], 'steps': steps},
            'bindings': [binding],
            'limits': {'max_log_bytes': 1048576, 'max_artifact_bytes': 4194304,
                       'max_metadata_bytes': 16777216, 'termination_grace_seconds': 1},
        },
        'normalizers': [],
    }
    validate('collection_request', request)
    return request


def role(fact, field, path):
    matches = [row['artifact_id'] for row in fact['binding'][field] if row['path'] == path]
    assert len(matches) == 1, (field, path, matches)
    return matches[0]


def log(parent, fact, stream):
    return parent.read_bytes(fact['binding']['log_artifacts'][stream])


def selected_usage(parent, subject, fact, header_id):
    name = fact['receipt']['id']
    depfile = role(fact, 'output_artifacts', f'build/{name}.d')
    usage = consumer.normalize_consumer_usage(
        parent, subject, usage_id=f'{name}-header-use', receipt_id=name,
        configuration_probe_receipt_id='configuration', target_probe_receipt_id='target',
        required_artifact_ids=[header_id], depfile_artifact_ids=[depfile],
    )
    assert usage['status'] == 'verified', usage['limitations']
    assert usage['compiler_version'] == '14.2.0' and usage['linker_version'] == '2.44', usage
    assert usage['context_id'] == CONTEXT and usage['proof_receipt_ids'] == [name, 'configuration', 'target']
    assert usage['records'] == [{'distribution_artifact_id': header_id, 'proof_kind': 'depfile',
                                  'proof_artifact_id': depfile, 'members': [HEADER]}]
    configuration = usage['observed_configuration']
    assert configuration['linking'] == 'header-only'
    assert configuration['language_standard'] == 'c++17' and configuration['target'] == 'x86_64-linux-gnu'
    assert configuration['macros'] == {'SELECTED_MACRO': '7'}
    assert any('not exhaustive template coverage' in item for item in usage['limitations'])
    return usage


def scenario_matrix(local, subject, base_case, name):
    case = deepcopy(base_case)
    if name == 'omit-selfcontainment':
        case['usage_ids'] = case['usage_ids'][:1]
    elif name == 'missing-named-test':
        case['tests'] = [MISSING_TEST]
    return consumer.declare_consumer_matrix(
        local, subject, matrix_id=name + '-matrix', cases=[case], limitations=[LIMIT],
    )


def comparison_reports(out, name, published, comparison, usages):
    path = published.path.parents[1]
    format_receipts = {}
    for fmt in ('json', 'html'):
        destination = out / f'{name}-report.{fmt}'
        result = external(out, f'{name}-report-{fmt}',
                          [CLI, 'report', '--input', path, '--evidence',
                           '--run-id', published.run_id, '--manifest-sha256', published.manifest_sha256,
                           '--format', fmt, '--output', destination])
        assert result['run_id'] == published.run_id and result['manifest_sha256'] == published.manifest_sha256
        content = destination.read_bytes()
        assert result['bytes'] == len(content) and result['mode'] == 'snapshot_view'
        if fmt == 'json':
            view = json.loads(content)
            validate('snapshot_view', view)
            facts = {'consumer_comparison': [comparison], 'consumer_usage': usages}
            for kind, expected in facts.items():
                rows = [fact for fact in view['facts'] if fact['kind'] == kind]
                for row in rows:
                    raw = row['raw_json'].encode()
                    assert raw == published.read_bytes(row['artifact_id']) and sha(raw) == row['sha256']
                bodies = [json.loads(fact['raw_json']) for fact in rows]
                assert sorted(bodies, key=lambda body: body['id']) == sorted(expected, key=lambda body: body['id'])
            assert LIMIT in view['limitations'] and view['assessment'] is None
        else:
            display = html.unescape(content.decode())
            assert f"Consumer applicability: {comparison['id']}" in display and LIMIT in display
            case = comparison['cases'][0]
            assert f"compatible / {case['local_test_status']}" in display
            assert all(check in display for check in case['missing_local_checks'])
        format_receipts[fmt] = {'sha256': sha(content), 'bytes': len(content), 'exit': 0}
    return format_receipts


def main():
    out = Path(sys.argv[1]).resolve(strict=True)
    assert Path.cwd() == out / 'outside' and Path.home().resolve() == Path('/home/agent')
    assert not list(Path.home().iterdir()), Path.home()
    assert Path(cppulse.__file__).resolve().is_relative_to(INSTALLED / 'cppulse')
    assert Path(consumer.__file__).resolve() == INSTALLED / 'cppulse/consumer.py'
    assert shutil.which('cppulse') == str(CLI)
    candidate = installed_candidate()
    workspace = out / 'project'
    shutil.copytree(INPUT, workspace)
    (workspace / 'build').mkdir()
    store = out / 'store'
    request = request_document(workspace)
    request_path = out / 'collection-request.json'
    write_json(request_path, request)
    collected = external(out, 'collect', [CLI, 'collect', '--request', request_path,
                                         '--workspace', workspace, '--store', store], timeout=180)
    assert collected['status'] == 'completed' and collected['exit_code'] == 0, collected
    run_store = RunStore(store)
    original = collected['final_run']
    parent = run_store.open_run(original['run_id'], manifest_sha256=original['manifest_sha256'])
    ensure_current_materials(parent, workspace)
    docs = read_documents(parent)
    facts = {row['receipt']['id']: row for row in docs['execution_facts']}
    assert set(facts) == {row['id'] for row in request['plan']['recipe']['steps']}
    tests = facts['tests']
    counts = {'total': 2, 'passed': 2, 'failed': 0, 'skipped': 0, 'errors': 0}
    assert tests['receipt']['exit_code'] == 0 and tests['receipt']['tests'] == counts
    assert tests['binding']['status'] == 'verified' and tests['material_status'] == 'available'
    evidence = next(row for document in docs['evidence'] for row in document['records'] if row['id'] == NAMED_TEST)
    assert evidence['origin'] == 'execution' and evidence['usability'] == 'usable'
    assert evidence['producer']['version'] == '3.31.6' and len(evidence['scope']['tests']) == 2
    inventory = json.loads(log(parent, facts['inventory'], 'stdout'))
    assert {row['name'] for row in inventory['tests']} == EXPECTED_CTEST
    for step_name, binary in [('consumer', 'build/selected-consumer'), ('selfcontained', 'build/standalone-header')]:
        original_binary = parent.read_bytes(role(facts[step_name], 'output_artifacts', binary))
        assert parent.read_bytes(role(tests, 'input_artifacts', binary)) == original_binary
        assert parent.read_bytes(role(facts['inventory'], 'input_artifacts', binary)) == original_binary
    junit_id = role(tests, 'output_artifacts', 'build/junit.xml')
    last_test_id = role(tests, 'output_artifacts', 'build/Testing/Temporary/LastTest.log')
    junit, last_test = parent.read_bytes(junit_id), parent.read_bytes(last_test_id)
    assert {row.get('name') for row in ET.fromstring(junit).iter('testcase')} == EXPECTED_CTEST
    assert all(label.encode() in last_test for label in EXPECTED_CTEST)
    assert last_test.count(b'Test Passed.') == 2, last_test

    header_id = role(facts['consumer'], 'input_artifacts', HEADER)
    copy_id = role(facts['selfcontained'], 'input_artifacts', HEADER)
    assert parent.read_bytes(header_id) == parent.read_bytes(copy_id) == (INPUT / HEADER).read_bytes()
    subject = consumer.describe_distribution(parent, subject_id='selected-header', kind='header-only',
                                             distribution_files={LOGICAL_HEADER: header_id},
                                             source_files=[HEADER], limitations=[LIMIT])
    usages = [selected_usage(parent, subject, facts[name], header_id) for name in ('consumer', 'selfcontained')]
    assert usages[0]['self_containment_headers'] == []
    assert usages[1]['self_containment_headers'] == [LOGICAL_HEADER]
    assert usages[0]['observed_configuration'] == usages[1]['observed_configuration']
    base_case = {'id': 'selected-int-macro7', 'required': True, 'context_id': CONTEXT,
                 'configuration': usages[0]['observed_configuration'], 'tests': [NAMED_TEST],
                 'instantiations': [INSTANTIATION], 'self_containment_headers': [LOGICAL_HEADER],
                 'usage_ids': [usage['id'] for usage in usages]}
    positive_matrix = scenario_matrix(parent, subject, base_case, 'positive')
    local = consumer.persist_consumer_documents(
        parent, [('distribution_subject', subject), *[('consumer_usage', usage) for usage in usages],
                 ('consumer_matrix', positive_matrix)], workspace=workspace, store=run_store,
    )
    write_json(out / 'subject.json', subject)
    write_json(out / 'usages.json', usages)

    expected = {
        'positive': ('passed', [], [NAMED_TEST]),
        'omit-selfcontainment': ('passed', [LOGICAL_HEADER], [NAMED_TEST]),
        'missing-named-test': ('unknown', [MISSING_TEST, 'selected-instantiation:' + INSTANTIATION], []),
    }
    variants = {}
    for name, outcome in expected.items():
        matrix = scenario_matrix(parent, subject, base_case, name)
        variant = consumer.persist_consumer_documents(
            local, [('consumer_matrix', matrix)], workspace=workspace, store=run_store)
        comparison = consumer.compare_consumers(
            local, variant, upstream_subject_id=subject['id'], local_subject_id=subject['id'],
            upstream_matrix_id=positive_matrix['id'], local_matrix_id=matrix['id'],
            generated_at=datetime.now(timezone.utc).isoformat(), comparison_id='fr07-' + name,
        )
        case, = comparison.document['cases']
        assert case['status'] == 'compatible' and case['mismatches'] == []
        actual = (case['local_test_status'], case['missing_local_checks'], case['local_test_evidence_ids'])
        assert actual == outcome, (name, actual, outcome)
        assert {'selected-instantiation:' + INSTANTIATION, LOGICAL_HEADER} <= set(case['required_local_checks'])
        assert comparison.document['authentication'] == 'unverified'
        write_json(out / f'{name}-matrix.json', matrix)
        write_json(out / f'{name}-comparison.json', comparison.document)
        published = consumer.persist_consumer_documents(
            variant, [('consumer_comparison', comparison.document)], raw_artifacts=comparison.artifacts,
            workspace=workspace, store=run_store,
        )
        pinned = RunStore.open_existing(store).open_run(**pin(published))
        for blob in comparison.artifacts:
            assert pinned.read_bytes(blob.id) == blob.content
        ensure_current_materials(pinned, workspace)
        variants[name] = {'matrix_id': matrix['id'], 'comparison_id': comparison.document['id'],
                          'run': pin(pinned), 'case': case,
                          'reports': comparison_reports(out, name, pinned, comparison.document, usages)}

    ensure_current_materials(parent, workspace)
    for filename in request['source']['files']:
        assert (workspace / filename).read_bytes() == (INPUT / filename).read_bytes()
    assert installed_candidate() == candidate
    write_json(out / 'qualification.json', {
        'criterion': 'FR-EVD-07', 'fixture': 'fresh finite authored producer', 'scope': LIMIT,
        'candidate': candidate,
        'collection': pin(parent), 'observed_matrix': pin(local), 'package_root': str(INSTALLED),
        'account_home': str(Path.home()), 'capture_tool_versions': {'gcc': '14.2.0', 'ld': '2.44', 'ctest': '3.31.6'},
        'ctest_cases': sorted(EXPECTED_CTEST), 'counts': counts,
        'junit': {'artifact_id': junit_id, 'sha256': sha(junit)},
        'last_test': {'artifact_id': last_test_id, 'sha256': sha(last_test)},
        'usage_ids': [usage['id'] for usage in usages], 'variants': variants,
    })
    print('FR-EVD-07 recorded both actual CTest cases and six pinned reports')


if __name__ == '__main__':
    main()
