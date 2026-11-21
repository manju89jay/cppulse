"""Run the eight original FR-GIT-01 public checks with fresh local equivalents."""

import errno
import hashlib
import json
import os
from pathlib import Path
import pwd
import socket
import subprocess
import sys

from fixture import GIT, declare, inventory, materialize


BASE = Path(__file__).resolve().parent
WORK = Path('/workspace/work')
CURRENT = WORK / 'attribution-epoch'
INSTALLED = CURRENT / 'candidate/installed'
INSTALL = CURRENT / 'installed/exact-payloads.json'
EARLIER = WORK / 'current38-next/public-flow/history-receipt/history-public'
READBACK = WORK / 'current38-history-next/results/history-readback/receipt.json'
TREE = '1e950418b3eed8c7e81c07277349c484b64db0b0'
WHEEL = '4d2e3907b78f8f0628a33a0ab235eb58bf755064ca1ae21678f90a848bfde654'
GIT_SHA = '356db14e102d68a1a37d8a1ac577dfd678d45d46e92f468bef8b7154e7bfdc60'
SCOPE_NOTE = ('Legacy file metrics use the retained history scope. The configured behavior '
              'lookback and cutoff apply only to behavioral metrics; history collection '
              'bounds and other limitations still apply.')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def package_origins():
    pins = read(INSTALL)['namespace_payloads']
    result = {}
    for name, module in sorted(sys.modules.items()):
        if name == 'cppulse' or name.startswith('cppulse.'):
            path = Path(module.__file__).resolve(strict=True)
            relative = path.relative_to(INSTALLED / 'cppulse').as_posix()
            digest = sha(path)
            assert digest == pins[relative]['sha256'], name
            result[name] = {'path': str(path), 'sha256': digest}
    assert 'cppulse.git_miner.main' in result
    return result


def preflight(out):
    import cppulse.git_miner.main

    home = Path.home()
    assert home == Path(pwd.getpwuid(os.getuid()).pw_dir) and not any(home.iterdir())
    assert Path.cwd() == out / 'outside'
    assert Path(sys.prefix) == Path('/workspace/verification-python-venv')
    assert os.environ['PYTHONPATH'] == str(INSTALLED)
    assert sha(GIT) == GIT_SHA
    assert {path.name for path in Path('/sys/class/net').iterdir()} == {'lo'}
    blocked = {}
    for family in (socket.AF_INET, socket.AF_INET6, socket.AF_UNIX):
        try:
            with socket.socket(family):
                raise AssertionError(f'{family.name} socket unexpectedly available')
        except OSError as failure:
            assert failure.errno == errno.ENETUNREACH
            blocked[family.name] = failure.errno
    pin = read(INSTALL)
    assert pin['wheel_sha256'] == sha(Path(pin['wheel'])) == WHEEL
    write(out / 'preflight.json', {
        'candidate_tree': TREE, 'wheel_sha256': WHEEL,
        'initially_empty_account_home': str(home), 'socket_denial': blocked,
        'git_sha256': sha(GIT), 'git_version': subprocess.check_output([GIT, '--version'], text=True).strip(),
        'module_origins': package_origins(),
    })


def behavior_request(window):
    return {
        'version': '1.0.0', 'window_days': window, 'half_life_days': 10,
        'max_commits': 100, 'max_files_per_commit': 20, 'max_pair_records': 100,
        'minimum_support': 2, 'aliases': {}, 'bot_ids': [], 'former_contributor_ids': [],
        'offboarding_ids': [], 'teams': {}, 'components': {}, 'exclude_paths': [],
        'exclude_commit_ids': [], 'include_merges': False, 'pair_attribution': 'author_only',
    }


def call(out, fixtures, case, cutoff):
    where = out / case['label']
    where.mkdir()
    output = where / 'outputs'
    argv = [sys.executable, '-B', '-m', 'cppulse.git_miner.main',
            '--repo', str(fixtures / case['repo']), '--output', str(output), '--szz-cutoff', cutoff]
    if 'window' in case:
        requested = where / 'requested-config.json'
        write(requested, behavior_request(case['window']))
        argv += ['--behavior-config', str(requested), '--behavior-cutoff', cutoff]
    finished = subprocess.run(argv, capture_output=True, timeout=120)
    (where / 'stdout').write_bytes(finished.stdout)
    (where / 'stderr').write_bytes(finished.stderr)
    receipt = {'argv': argv, 'cwd': str(Path.cwd()), 'exit_status': finished.returncode,
               'expected_exit': case['exit']}
    write(where / 'command.json', receipt)
    return receipt


def verify_shapes(out, spec, heads):
    from cppulse.contracts import validate
    from cppulse.git_miner.behavior import validate_behavior_report
    from cppulse.git_miner.history_cache import validate_history_document

    expected = spec['expected']
    failures = []
    summaries = {}
    validated = {}

    def check(label, condition, detail):
        if not condition:
            failures.append({'case': label, 'detail': detail})

    for case in spec['cases']:
        label = case['label']
        where = out / label
        target = where / 'outputs'
        command = read(where / 'command.json')
        summary = summaries[label] = {'exit_status': command['exit_status']}
        check(label, command['exit_status'] == case['exit'], 'Unexpected public process exit.')
        if case['exit']:
            diagnostic = (where / 'stderr').read_text(errors='replace').casefold()
            text = 'invalid behavior request' if 'window' in case else 'repository path does not exist'
            check(label, text in diagnostic, f'Missing meaningful refusal diagnostic: {text}.')
            check(label, not target.exists(), 'Invalid request created a primary output directory.')
            continue

        try:
            legacy = read(target / 'git_metrics.json')
            validate('git_metrics', legacy, version='prototype_v1')
            history_path = target / 'git_history.json'
            behavior_path = target / 'git_behavior.json'
            history = read(history_path) if history_path.is_file() else None
            behavior = read(behavior_path) if behavior_path.is_file() else None
            if history is not None:
                validate_history_document('result', history)
            if behavior is not None:
                validate_behavior_report(behavior)
            validated[label] = (legacy, history, behavior)
        except Exception as failure:
            failures.append({'case': label, 'detail': f'{type(failure).__name__}: {failure}'})
            continue

        meta = legacy['metadata']
        rows = {row['file']: row for row in legacy['file_metrics']}
        summary.update({
            'availability': meta['history_status'], 'commits': meta['total_commits'],
            'metrics_files': sorted(rows), 'legacy_scope_note': SCOPE_NOTE in meta['limitations'],
            'history_scope_note': history is not None and SCOPE_NOTE in history['limitations'],
            'legacy_sha256': sha(target / 'git_metrics.json'),
            'history_sha256': sha(history_path) if history is not None else None,
            'behavior_sha256': sha(behavior_path) if behavior is not None else None,
        })
        if case['repo'] in ('absent', 'unborn'):
            check(label, meta['history_status'] == 'unavailable' and meta['total_commits'] == 0
                  and meta['commit_range'] == 'empty' and not rows and not legacy['knowledge_silos'],
                  'Absent or unborn history was represented as available or assigned legacy data.')
            check(label, behavior is None, 'Unrequested behavior output appeared.')
            if case['repo'] == 'absent':
                check(label, history is None and any('no git repository' in note.casefold()
                      for note in meta['limitations']), 'Absent repository lacked explicit history absence.')
            else:
                check(label, history is not None and history['head'] is None and history['selection']['count'] == 0
                      and any('no readable commit history' in note.casefold() for note in history['limitations']),
                      'Unborn Git metadata failed to disclose the empty history selection.')
            continue

        check(label, sorted(rows) == expected['current_files'],
              'Renamed or deleted paths are duplicated in current-file metrics.')
        check(label, history is not None and history['head'] == heads['head'],
              'History output fails to bind the verified fixture HEAD.')
        if case['repo'] == 'shallow':
            check(label, meta['history_status'] == 'partial' and meta['total_commits'] == 1,
                  'The actual depth-1 boundary was not published as one partial commit.')
            check(label, history is not None and history['selection']['count'] == 1
                  and history['selected_records_complete'] is False
                  and any('shallow history' in note.casefold() for note in history['limitations']),
                  'Checked history omitted the unavailable shallow delta.')
            check(label, all(row['change_frequency'] == row['lines_added_total'] == row['lines_removed_total'] == 0
                             for row in rows.values()), 'Unknown-parent delta introduced positive legacy changes.')
            continue

        check(label, meta['history_status'] == 'partial' and meta['total_commits'] == expected['repository_commits']
              and (history is not None and history['selection']['count'] == expected['repository_commits']),
              'The real merge was not retained with a partial six-commit history.')
        check(label, any('first-parent' in note and 'cross-branch rename lineage' in note
                         for note in meta['limitations']), 'First-parent merge limitation was lost.')
        renamed = expected['renamed']
        check(label, all(rows.get(renamed['file'], {}).get(key) == value for key, value in renamed.items()),
              'Rename lineage no longer retains exactly three changes and 31 current lines.')
        if 'window' not in case:
            check(label, behavior is None and history is not None and SCOPE_NOTE not in history['limitations'],
                  'Default run unexpectedly included a behavioral window or history-sidecar scope note.')
            check(label, SCOPE_NOTE not in meta['limitations'],
                  'Default legacy metrics include the behavioral-window note without a configured behavior request.')
            continue

        days = case['window']
        check(label, SCOPE_NOTE in meta['limitations'] and history is not None
              and SCOPE_NOTE in history['limitations'] and '90' not in SCOPE_NOTE,
              'Configured behavior window lacks its distinct legacy and history scope disclosure.')
        exclusions = expected[f'window{days}']
        summary['behavior_counts'] = None if behavior is None else behavior['counts']
        check(label, behavior is not None and behavior['head'] == heads['head']
              and behavior['configuration']['window_days'] == days
              and behavior['cutoff'] == spec['cutoff'].replace('Z', '+00:00')
              and behavior['counts']['excluded_commits'] == exclusions
              and behavior['counts']['observed_commits'] == expected['repository_commits']
              and behavior['counts']['accepted_commits'] == expected['repository_commits'] - sum(exclusions.values()),
              f'{days}-day behavior window did not apply the preregistered acceptance and exclusions.')

    default = validated.get('default-full-history')
    for label in ('seven-day-window', 'two-day-window'):
        selected = validated.get(label)
        check(label, default is not None and selected is not None
              and default[0]['file_metrics'] == selected[0]['file_metrics'],
              'Configured behavior window changed legacy file-metric values.')
        check(label, default is not None and selected is not None and default[1] is not None
              and selected[1] is not None and all(default[1][key] == selected[1][key] for key in
                   ('head', 'checkpoint_sha256', 'selection', 'current_files_digest', 'selected_records_complete')),
              'Configured window modified shared raw history identity or selection.')
    return summaries, failures


def known_current_history():
    from cppulse.contracts import validate
    from cppulse.contracts.history_contract import validate_history_binding

    prior = read(READBACK)
    recorded = read(EARLIER / 'qualification.json')
    assert prior['wheel_sha256'] == recorded['wheel_sha256'] == WHEEL
    assert prior['qualification_sha256'] == sha(EARLIER / 'qualification.json')
    assert prior['manifest_sha256'] == recorded['manifest_sha256'] and prior['run_id'] == recorded['run_id']
    typed = read(EARLIER / 'shared-history.json')
    validate('shared_history', typed)
    validate_history_binding(typed, source_digest=recorded['source_digest'], context_id=recorded['context_id'])
    return {'prior_receipt_sha256': sha(READBACK), 'typed_history_sha256': sha(EARLIER / 'shared-history.json'),
            'run_id': prior['run_id'], 'manifest_sha256': prior['manifest_sha256'],
            'same_installed_wheel': True, 'independent_support_only': True}


def main(out):
    preflight(out)
    specification = BASE / 'fixture.json'
    declared = BASE / 'objects.json'
    spec = read(specification)
    objects = read(declared)
    assert declare(spec) == objects
    assert len(spec['cases']) == 8 and len(objects) == spec['expected']['repository_commits']
    fixtures = out / 'fixtures'
    fixtures.mkdir()
    before = materialize(fixtures, objects, spec['expected']['shallow_depth'])
    write(out / 'repository-before.json', before)
    for case in spec['cases']:
        call(out, fixtures, case, spec['cutoff'])
    after = inventory(fixtures, objects)
    write(out / 'repository-after.json', after)
    summaries, failures = verify_shapes(out, spec, before)
    if before != after:
        failures.append({'case': 'fixtures', 'detail': 'Public commands changed the frozen repository inputs.'})
    supporting = known_current_history()
    write(out / 'qualification.json', {
        'status': 'failed' if failures else 'passed',
        'criterion': 'FR-GIT-01', 'candidate_tree': TREE, 'wheel_sha256': WHEEL,
        'new_history_scope': spec['custody'], 'configuration_sha256': sha(specification),
        'preregistered_objects_sha256': sha(declared), 'repository_immutable': before == after,
        'case_count': len(summaries), 'results': summaries, 'nonpassing': failures,
        'known_current_typed_history_support': supporting, 'module_origins': package_origins(),
    })
    for failure in failures:
        print(f"{failure['case']}: {failure['detail']}")
    print(f'FR-GIT-01 recorded {len(summaries)} public cases with {len(failures)} nonpassing assertions')
    return int(bool(failures))


if __name__ == '__main__':
    sys.exit(main(Path(sys.argv[1])))
