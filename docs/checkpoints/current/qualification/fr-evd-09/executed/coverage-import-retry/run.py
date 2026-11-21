"""Repeat only the two import controls with a preregistered RFC 3339 UTC time."""

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import runpy
import stat
import sys

import cppulse
from cppulse.contracts import validate_evaluation_policy
from cppulse.policy import evaluate_policy
from cppulse.workflows import read_documents


LANE = Path(__file__).resolve().parent
BASE = LANE.parent
PRIOR = BASE / 'continuation-results'
PREVIOUS = runpy.run_path(str(BASE / 'coverage-continuation/run.py'))
OLD = PREVIOUS['OLD_CODE']
WORKSPACE = PREVIOUS['WORKSPACE']


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(root):
    entries = {}
    for directory, directories, filenames in os.walk(root, followlinks=False):
        for name in sorted(directories + filenames):
            path = Path(directory) / name
            mode = path.lstat().st_mode
            key = path.relative_to(root).as_posix()
            if stat.S_ISLNK(mode):
                target = os.readlink(path)
                assert path.resolve(strict=True).is_relative_to(root), (path, target)
                entries[key] = {'type': 'symlink', 'mode': stat.S_IMODE(mode), 'target': target}
            elif stat.S_ISREG(mode):
                entries[key] = {'type': 'file', 'mode': stat.S_IMODE(mode), 'sha256': digest(path)}
            else:
                assert stat.S_ISDIR(mode), path
                entries[key] = {'type': 'directory', 'mode': stat.S_IMODE(mode)}
        directories.sort()
    return entries


def registration():
    frozen = json.loads((LANE / 'sealed-retry-inputs.json').read_bytes())
    reference = Path(frozen['assessment_clock_artifact'])
    assert digest(reference) == frozen['assessment_clock_artifact_sha256']
    assert json.loads(reference.read_bytes())['generated_at'] == frozen['evaluation_time']
    timestamp = datetime.fromisoformat(frozen['evaluation_time'].replace('Z', '+00:00'))
    assert frozen['evaluation_time'].endswith('Z') and timestamp.utcoffset().total_seconds() == 0
    return frozen


def custody(out, phase):
    if phase == 'before':
        assert Path.home() == Path('/home/agent') and not list(Path.home().iterdir())
    frozen = registration()
    assert inventory(PRIOR) == frozen['continuation_results']
    assert PREVIOUS['custody']() == json.loads((PRIOR / 'custody-before.json').read_bytes())
    assert (PRIOR / 'custody-before.json').read_bytes() == (PRIOR / 'custody-after.json').read_bytes()
    for name in ('lcov', 'cobertura', 'invalid', 'm5-policy115'):
        assert (PRIOR / name / 'phase.exit').read_text().strip() == '0'
        assert (PRIOR / name / 'phase-result.json').is_file()
    for adapter in ('lcov', 'cobertura'):
        phase_dir = PRIOR / f'import-{adapter}'
        assert (phase_dir / 'phase.exit').read_text().strip() == '1'
        assert 'generated_at must be an explicit RFC3339 UTC time' in (phase_dir / 'phase.stderr').read_text()
    OLD['write_json'](out / f'custody-{phase}.json', {
        'original_producer': frozen['original_producer'],
        'prior_continuation_manifest_sha256': digest(LANE / 'sealed-retry-inputs.json'),
        'prior_continuation_entries': len(frozen['continuation_results']),
        'original_and_continuation_results_unchanged': True,
        'evaluation_time': frozen['evaluation_time'],
    })


def import_retry(out, adapter):
    root, selections, _ = PREVIOUS['producer']()
    frozen = registration()
    assert PREVIOUS['pin'](root) == frozen['original_producer']
    assert datetime.fromisoformat(frozen['evaluation_time'].replace('Z', '+00:00')) >= datetime.fromisoformat(
        root.manifest['finished_at'].replace('Z', '+00:00'))
    imported, fact = OLD['make_import'](out, root, WORKSPACE, adapter, selections[adapter])
    name = f'{adapter}-import'
    document = OLD['policy'](name, fact, [OLD['control'](fact, kind, method)
                            for kind, method in OLD['METHODS'][adapter].items()])
    validate_evaluation_policy(document)
    file = out / f'{name}-policy.json'
    OLD['write_json'](file, document)
    observed = evaluate_policy(document, read_documents(imported), generated_at=frozen['evaluation_time'])
    OLD['write_json'](out / f'{name}-pure-evaluation.json', observed)
    assert observed['gate'] == 'insufficient_evidence' and {row['status'] for row in observed['controls']} == {'unknown'}
    assert len(observed['controls']) == 3
    responses = {}
    for verb in ('assess', 'check'):
        _, response = OLD['policy_command'](out, name, verb, imported, WORKSPACE, file, 3)
        assert response['assessment_artifact_id'] is None
        assert response['error']['code'] == 'UNVERIFIED_SOURCE', response
        responses[verb] = {'exit': 3, 'error': response['error']}
    OLD['write_json'](out / 'phase-result.json', {'run': OLD['pin'](imported), 'responses': responses,
                     'reports': OLD['typed_reports'](out, name, imported, fact)})


if __name__ == '__main__':
    phase, out_arg = sys.argv[1:]
    out = Path(out_arg).resolve(strict=True)
    assert Path(cppulse.__file__).resolve().is_relative_to(OLD['INSTALLED'] / 'cppulse')
    if phase in ('before', 'after'):
        custody(out, phase)
    else:
        assert phase in ('lcov', 'cobertura')
        import_retry(out, phase)
