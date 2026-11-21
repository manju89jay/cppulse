"""Fresh installed acquisition, mixed immutable evidence and public controls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import cppulse
from cppulse.run_store import RunStore
from cppulse.test_import import persist_test_import
from cppulse.workflows import ensure_current_materials, read_documents

WORK = Path('/workspace/work')
SOURCE = WORK / 'attribution-epoch/checkout'
INSTALLED = WORK / 'attribution-epoch/candidate/installed'
PROVENANCE = 'Synthetic test fixture claim about the selected retained CTest artifact.'
EXPIRY = '2026-12-13T12:00:00Z'


def invoke(out, label, argv, expected, *, json_stdout=True):
    result = subprocess.run(argv, cwd=out, capture_output=True, timeout=120)
    (out / (label + '.stdout')).write_bytes(result.stdout)
    (out / (label + '.stderr')).write_bytes(result.stderr)
    (out / (label + '.receipt.json')).write_text(
        json.dumps({'argv': [str(x) for x in argv], 'cwd': str(out),
                    'exit_code': result.returncode, 'expected_exit': expected}, indent=2) + '\n')
    assert result.returncode == expected, (label, result.returncode, result.stdout, result.stderr)
    return json.loads(result.stdout) if json_stdout else None


def fixed(snapshot):
    return ['--run-id', snapshot.run_id, '--manifest-sha256', snapshot.manifest_sha256]


def supply_attestations(parent, workspace, store, imported, report):
    review = {
        'id': 'fixture-review',
        'context_id': imported['context_id'],
        'producer': {'name': 'fixture-author', 'version': '1.0.0'},
        'origin': 'attestation', 'kind': 'review', 'status': 'passed',
        'usability': 'usable', 'artifact_ids': [report['id']], 'receipt_id': None,
        'scope': imported['scope'],
        'reviewer': 'controlled-reviewer', 'expires_at': EXPIRY,
        'limitations': ['Synthetic caller-supplied review; identity is unauthenticated.'],
        'review_details': {
            'version': '1.0.0', 'source_digest': parent.manifest['source']['digest'],
            'statement': 'The selected CTest artifact is identified by its retained digest.',
            'rationale': PROVENANCE,
            'reviewed_at': '2026-11-13T10:00:00Z',
            'recorded_at': '2026-11-13T10:01:00Z', 'recorded_by': 'fixture-author',
            'reviewed_artifact_ids': [report['id']],
            'reviewed_artifact_sha256': {report['id']: report['sha256']},
            'identity_assurance': 'self_declared',
            'limitations': ['Reviewer identity has not been authenticated.'],
        },
    }
    attestation = {key: value for key, value in imported.items() if key not in {'import_adapter', 'test_counts', 'test_cases'}}
    attestation.update(
        id='fixture-attested-tests', origin='attestation', receipt_id=None,
        reviewer=review['reviewer'], expires_at=review['expires_at'],
        producer=review['producer'], limitations=['Synthetic supplied test claim.'])
    evidence = {'version': '2.0.0', 'source_digest': review['review_details']['source_digest'],
                'records': [attestation, review]}
    with store.begin() as stage:
        for row in parent.manifest['artifacts']:
            copied = stage.copy_artifact(row['id'], parent.path / row['path'],
                                         row['path'], row['media_type'],
                                         contract=row.get('contract'))
            assert copied == row
        stage.write_json('evidence/qualification-fixture.json', evidence,
                         artifact_id='qualification-fixture', contract='evidence')
        manifest = parent.manifest
        manifest.update(run_id=stage.run_id, artifacts=stage.artifacts)
        child = stage.publish(manifest, source_check=lambda: ensure_current_materials(parent, workspace))
    child.verify()
    assert child.manifest['input_verification'] == 'verified'
    return child, attestation, review


def main(out):
    assert Path(cppulse.__file__).resolve().is_relative_to(INSTALLED / 'cppulse')
    assert not any(Path.home().iterdir()), Path.home()
    workspace, store_path = out / 'trial', out / 'store'
    cli = INSTALLED / 'bin/cppulse'
    invoke(out, 'prepare', [sys.executable, SOURCE / 'examples/first-trial/prepare.py',
                            '--workspace', workspace], 0)
    capture = invoke(out, 'collect', [cli, 'collect', '--request',
                     workspace / 'collection-request.json', '--workspace', workspace,
                     '--store', store_path], 0)
    assert capture['status'] == 'completed'
    store = RunStore(store_path)
    base = store.open_run(**{key: capture['final_run'][key]
                            for key in ('run_id', 'manifest_sha256')})
    ensure_current_materials(base, workspace)
    docs = read_documents(base)
    execution = next(row for doc in docs['evidence'] for row in doc['records']
                     if row['id'] == 'trial-tests')
    fact = next(row for row in docs['execution_facts'] if row['receipt']['id'] == 'tests')
    assert fact['receipt']['tests'] == {'total': 3, 'passed': 3, 'failed': 0,
                                        'skipped': 0, 'errors': 0}
    assert execution['origin'] == 'execution' and execution['receipt_id'] == 'tests'
    expected = next(row for row in fact['output_facts'] if row['path'] == 'build/junit.xml')
    report = next(row for row in base.manifest['artifacts']
                  if row['id'] in execution['artifact_ids'] and row['sha256'] == expected['sha256'])
    assert report['size_bytes'] == expected['size_bytes']
    raw = base.read_bytes(report['id'])
    assert raw == (workspace / 'build/junit.xml').read_bytes()

    imported_snapshot = persist_test_import(
        base, workspace=workspace, store=store, report_artifact_id=report['id'],
        context_id=execution['context_id'], scope_files=execution['scope']['files'],
        adapter='ctest-junit', producer={'name': 'ctest', 'version': '3.31.6'})
    imported = next(row for doc in read_documents(imported_snapshot)['evidence']
                    for row in doc['records'] if row['origin'] == 'import')
    assert imported['scope']['tests'] == execution['scope']['tests']
    assert imported['context_id'] == execution['context_id']
    assert imported['receipt_id'] is None and imported['artifact_ids'] == [report['id']]
    assert imported['status'] == 'passed' and imported['usability'] == 'usable'
    mixed, attestation, review = supply_attestations(
        imported_snapshot, workspace, store, imported, report)
    assert mixed.read_bytes(report['id']) == raw
    assert mixed.manifest['source'] == base.manifest['source']

    checks = {}
    original = json.loads((workspace / 'policy.json').read_bytes())
    for evidence, label, code, status in (
        (execution, 'execution', 0, 'passed'),
        (imported, 'import', 3, 'unknown'),
        (attestation, 'attestation', 3, 'unknown'),
    ):
        policy = deepcopy(original)
        policy['controls'][0]['parameters']['evidence_ids'] = [evidence['id']]
        path = out / ('policy-' + label + '.json')
        path.write_text(json.dumps(policy, indent=2) + '\n')
        checked = invoke(out, 'check-' + label, [cli, 'check', '--store', store_path,
                         '--workspace', workspace, *fixed(mixed), '--policy', path], code)
        assert checked['status'] == ('passed' if code == 0 else 'insufficient_evidence')
        result = store.open_run(checked['run']['run_id'],
                                manifest_sha256=checked['run']['manifest_sha256'])
        assessment = result.read_json(checked['assessment_artifact_id'])
        control = next(item for item in assessment['controls'] if item['id'] == 'tests')
        assert control['status'] == status, control
        assert control['context_ids'] == [execution['context_id']], control
        checks[label] = control

    for fmt in ('json', 'html'):
        path = out / ('mixed.' + fmt)
        invoke(out, 'report-' + fmt, [cli, 'report', '--input', store_path, '--evidence',
               *fixed(mixed), '--format', fmt, '--output', path], 0, json_stdout=False)
    html = (out / 'mixed.html').read_text()
    for text in ('Execution-derived', 'Imported producer claim', 'Human attestation',
                 review['reviewer'], PROVENANCE, EXPIRY, 'clamp.h', 'checks.cpp',
                 'self_declared', 'Reviewer identity has not been authenticated.',
                 imported['scope']['tests'][0]):
        assert text in html, text
    rendered = json.loads((out / 'mixed.json').read_bytes())
    rendered_evidence = [row for item in rendered['facts'] if item['kind'] == 'evidence'
                         for row in json.loads(item['raw_json'])['records']]
    for expected_record in (execution, imported, attestation, review):
        assert next(row for row in rendered_evidence if row['id'] == expected_record['id']) == expected_record
    ensure_current_materials(mixed, workspace)
    (out / 'qualification.json').write_text(json.dumps({
        'criterion': 'FR-EVD-05', 'package': cppulse.__file__,
        'source': mixed.manifest['source']['digest'], 'run': fixed(mixed),
        'same_junit_sha256': hashlib.sha256(raw).hexdigest(), 'case_ids': imported['scope']['tests'],
        'policy_results': checks, 'review_claim': review,
    }, indent=2) + '\n')


if __name__ == '__main__':
    main(Path(sys.argv[1]))
