"""Exercise the same eight public cases and the frozen changed Git regressions."""

from collections import Counter
from copy import deepcopy
from datetime import datetime
import errno
import os
from pathlib import Path
import pwd
import socket
import subprocess
import sys
import xml.etree.ElementTree as ET

from common import B6_DRIVER, B6_RESULT, CHECKOUT, GIT, GIT_SHA, file_map, read, sha, write

sys.path.insert(1, str(B6_DRIVER))
from fixture import declare, inventory
from recheck import SCOPE_NOTE, call, verify_shapes


def modules(root, pins):
    found = {}
    for name, module in sorted(sys.modules.items()):
        if name != 'cppulse' and not name.startswith('cppulse.'):
            continue
        source = Path(module.__file__).resolve(strict=True)
        relative = source.relative_to(root / 'cppulse').as_posix()
        digest = sha(source)
        assert digest == pins[relative], (name, source)
        found[name] = {'path': str(source), 'sha256': digest}
    assert 'cppulse.git_miner.main' in found
    return found


def preflight(group, out, registration):
    import cppulse.git_miner.main

    assert Path.cwd() == out / 'outside'
    home = Path.home()
    assert home == Path(pwd.getpwuid(os.getuid()).pw_dir) == Path('/home/agent') and not any(home.iterdir())
    assert sys.prefix == '/workspace/verification-python-venv'
    blocked = {}
    for family in (socket.AF_INET, socket.AF_INET6, socket.AF_UNIX):
        try:
            with socket.socket(family):
                raise AssertionError(f'Socket family unexpectedly allowed: {family}')
        except OSError as failure:
            assert failure.errno == errno.ENETUNREACH
            blocked[family.name] = failure.errno
    assert {name.name for name in Path('/sys/class/net').iterdir()} == {'lo'}
    assert sha(GIT) == GIT_SHA
    manifest_path = Path(registration['candidate_manifest'])
    assert sha(manifest_path) == registration['candidate_manifest_sha256']
    candidate = read(manifest_path)
    assert candidate['candidate_tree'] == registration['candidate_tree']
    assert candidate['wheel_sha256'] == sha(Path(candidate['wheel'])) == registration['wheel_sha256']
    if group == 'git-source':
        root = CHECKOUT / 'python'
        prefix = str(root / 'cppulse') + '/'
        pins = {path.removeprefix(prefix): digest for path, digest in registration['file_sha256'].items()
                if path.startswith(prefix)}
    else:
        root = Path(candidate['installed'])
        assert file_map(root) == candidate['installed_files']
        pins = {name: row['sha256'] for name, row in candidate['namespace_payloads'].items()}
    assert os.environ['PYTHONPATH'].split(':')[0] == str(root)
    write(out / 'preflight.json', {'tree': candidate['candidate_tree'], 'wheel_sha256': candidate['wheel_sha256'],
                                  'candidate_manifest_sha256': sha(manifest_path),
                                  'mode': 'source' if group == 'git-source' else 'installed',
                                  'socket_denial': blocked, 'ordinary_account_home': str(home),
                                  'git_sha256': GIT_SHA,
                                  'git_version': subprocess.check_output([GIT, '--version'], text=True).strip(),
                                  'origins': modules(root, pins)})
    return root, pins


def preserved_metrics(document, configured):
    copy = deepcopy(document)
    timestamp = copy['metadata'].pop('analyzed_at')
    assert datetime.fromisoformat(timestamp).tzinfo is not None
    notes = copy['metadata']['limitations']
    assert notes.count(SCOPE_NOTE) == int(configured)
    if configured:
        notes.remove(SCOPE_NOTE)
    return copy


def preserved_history(document, configured):
    copy = deepcopy(document)
    notes = copy['limitations']
    assert notes.count(SCOPE_NOTE) == int(configured)
    if configured:
        notes.remove(SCOPE_NOTE)
    return copy


def verify_extended(out, declaration):
    base = out / 'default-full-history/outputs'
    base_legacy = preserved_metrics(read(base / 'git_metrics.json'), False)
    base_history = preserved_history(read(base / 'git_history.json'), False)
    for case in declaration['cases']:
        folder = out / case['label']
        target = folder / 'outputs'
        if 'window' not in case and case['exit'] == 0:
            assert not (target / 'git_behavior.json').exists()
            assert SCOPE_NOTE not in (folder / 'stdout').read_text()
            assert SCOPE_NOTE not in (folder / 'stderr').read_text()
            assert SCOPE_NOTE not in read(target / 'git_metrics.json')['metadata']['limitations']
            history = target / 'git_history.json'
            if history.is_file():
                assert SCOPE_NOTE not in read(history)['limitations']
    for name in ('seven-day-window', 'two-day-window'):
        target = out / name / 'outputs'
        assert (target / 'git_behavior.json').is_file()
        assert preserved_metrics(read(target / 'git_metrics.json'), True) == base_legacy
        assert preserved_history(read(target / 'git_history.json'), True) == base_history
    return {'default_behavior_only_note_absent': True, 'default_behavior_report_absent': True,
            'configured_note_exactly_once_in_both_documents': True,
            'other_complete_legacy_documents_equal_excluding_generation_time_only': True,
            'other_complete_history_documents_equal': True}


def public_cases(out, registration, root, pins):
    spec_path = Path(registration['original_eight_registration'])
    spec = read(spec_path)
    objects = read(B6_DRIVER / 'objects.json')
    fixtures = Path(registration['fixture_dir'])
    assert declare(spec) == objects and len(spec['cases']) == 8
    before = inventory(fixtures, objects)
    assert before == read(B6_RESULT / 'repository-before.json')
    assert before['files'] == registration['fixture_files']
    write(out / 'repository-before.json', before)
    for case in spec['cases']:
        call(out, fixtures, case, spec['cutoff'])
    after = inventory(fixtures, objects)
    write(out / 'repository-after.json', after)
    summaries, failures = verify_shapes(out, spec, before)
    try:
        added_checks = verify_extended(out, spec)
    except Exception as failure:
        failures.append({'case': 'extended-scope-parity', 'detail': f'{type(failure).__name__}: {failure}'})
        added_checks = {}
    if before != after:
        failures.append({'case': 'fixtures', 'detail': 'Frozen original B6 fixture changed'})
    write(out / 'qualification.json', {
        'criterion': 'FR-GIT-01', 'status': 'failed' if failures else 'passed',
        'tree': registration['candidate_tree'], 'wheel_sha256': registration['wheel_sha256'],
        'case_count': len(summaries), 'results': summaries, 'nonpassing': failures,
        'additional_scope_predicates': added_checks, 'reused_exact_original_B6_fixture': str(fixtures),
        'prior_B6_red_qualification_sha256': sha(B6_RESULT / 'qualification.json'),
        'prior_B6_results_preserved': True, 'fixture_unchanged': before == after,
        'origins': modules(root, pins),
    })
    print(f'FR-GIT-01 {len(summaries)} original public cases, {len(failures)} nonpassing assertions')
    return int(bool(failures))


def regressions(out, registration, root, pins):
    import pytest
    from _pytest.junitxml import mangle_test_address

    test_ids = registration['test_nodeids']
    assert len(test_ids) == len(set(test_ids))
    selected = [str(CHECKOUT / node) for node in test_ids]
    file_paths = {str(CHECKOUT / node.split('::', 1)[0]) for node in test_ids}
    before = {name: sha(Path(name)) for name in file_paths}
    assert all(registration['file_sha256'][name] == digest for name, digest in before.items())

    class ExactCollection:
        def pytest_collection_finish(self, session):
            ids = [item.nodeid for item in session.items]
            assert Counter(ids) == Counter(test_ids)
            assert all(str(item.path) in file_paths for item in session.items)
            write(out / 'collection.json', {'nodeids': ids, 'file_sha256': before})

    xml = out / 'results.xml'
    argv = ['-q', '--import-mode=importlib', '-c', '/dev/null', f'--rootdir={CHECKOUT}',
            f'--confcutdir={CHECKOUT / "tests"}', '-p', 'no:cacheprovider',
            f'--junitxml={xml}', f'--basetemp={out / "fixtures"}', *selected]
    write(out / 'argv.json', argv)
    status = int(pytest.main(argv, plugins=[ExactCollection()]))
    rows = list(ET.parse(xml).iter('testcase'))
    seen = Counter((row.attrib['classname'], row.attrib['name']) for row in rows)
    expected = Counter()
    for case in test_ids:
        address = mangle_test_address(case)
        expected[('.'.join(address[:-1]), address[-1])] += 1
    assert seen == expected
    nonpasses = [{'case': row.attrib, 'outcome': entry.tag, 'message': entry.attrib.get('message')}
                 for row in rows for entry in row if entry.tag in ('error', 'failure', 'skipped')]
    assert before == {name: sha(Path(name)) for name in file_paths}
    write(out / 'qualification.json', {'tree': registration['candidate_tree'],
          'wheel_sha256': registration['wheel_sha256'], 'pytest_exit': status,
          'case_count': len(rows), 'nonpassing': nonpasses, 'junit_sha256': sha(xml),
          'source_before_after': before, 'origins': modules(root, pins)})
    print(f'{len(rows)} exact Git regressions, {len(nonpasses)} nonpassing')
    return status or int(bool(nonpasses))


def main(group, freeze, out):
    registration = read(freeze)
    assert registration['phase'] == 'tests'
    root, pins = preflight(group, out, registration)
    if group == 'git-public':
        return public_cases(out, registration, root, pins)
    assert group in ('git-installed', 'git-source')
    return regressions(out, registration, root, pins)


if __name__ == '__main__':
    group, freeze, output = sys.argv[1:]
    sys.exit(main(group, Path(freeze), Path(output)))
