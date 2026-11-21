"""Exercise the actual installed legacy CLI and native analysis on failure boundaries."""
import errno
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys

import cppulse
from cppulse.run_store import RunStore

out, candidate = map(Path, sys.argv[1:])
console = candidate / 'installed/bin/cppulse'
assert not any(Path.home().iterdir()), Path.home()
assert Path(cppulse.__file__).resolve().is_relative_to(candidate / 'installed/cppulse')
assert sorted(entry.name for entry in Path('/sys/class/net').iterdir()) == ['lo']
for family in (socket.AF_INET, socket.AF_INET6, socket.AF_UNIX):
    try:
        socket.socket(family)
    except OSError as error:
        assert error.errno == errno.ENETUNREACH
    else:
        raise AssertionError(f'Unexpected socket family access {family}')


def write(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def initialize(project, case):
    source = project / 'sample.cpp'
    if case != 'source-free':
        body = {
            'skipped': '// Too large for the selected sixteen-byte scope.\nvoid sample() {}\n',
            'parse-failed': '#error controlled native parser diagnostic\nvoid sample() {}\n',
        }.get(case, 'void sample() {}\n')
        source.write_text(body, encoding='utf-8')
    if case == 'skipped':
        write(project / '.cppulserc.json', {'max_file_bytes': 16})
    elif case == 'missing-detector':
        write(project / '.cppulserc.json', {'rules': {'CPP-MOD-001': {'enabled': False}}})
    elif case == 'unresolved-declared-context':
        other = project / 'covered.cpp'
        other.write_text('void covered() {}\n', encoding='utf-8')
        write(project / 'compile_commands.json', [{
            'directory': str(project), 'file': str(other),
            'arguments': ['clang++', '-x', 'c++', '-std=c++17', '-c', str(other)],
        }])
    elif case == 'declared-empty-database':
        write(project / 'compile_commands.json', [])


def identify(project):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(project.iterdir())}


def exercise(case):
    project = out / case
    store = out / (case + '-store')
    project.mkdir()
    initialize(project, case)
    before = identify(project)
    command = [console, 'analyze', '--repo', project, '--output', store, '--format', 'json',
               '--no-history', '--execution', 'legacy']
    if case in {'unresolved-declared-context', 'declared-empty-database'}:
        command += ['--compilation-database', project / 'compile_commands.json']
    finished = subprocess.run(command, cwd='/tmp', capture_output=True, timeout=120)
    write(out / (case + '.command.json'), {'argv': list(map(str, command)), 'exit': finished.returncode})
    (out / (case + '.stdout')).write_bytes(finished.stdout)
    (out / (case + '.stderr')).write_bytes(finished.stderr)
    assert finished.returncode == 3, (case, finished.returncode, finished.stderr)
    actual = json.loads(finished.stdout)
    assert actual['analysis_status'] == 'partial' and actual['input_verification'] == 'unverified'
    fixed = RunStore.open_existing(store).open_run(actual['run_id'],
                                                   manifest_sha256=actual['manifest_sha256'])
    assert fixed.manifest['contexts'] == []
    assert fixed.manifest['input_verification'] == 'unverified'
    assert fixed.read_json('risk_scores')['health_score']['overall'] is None
    assert fixed.read_json('normalized-risk')['health_score']['overall'] is None
    coverage = fixed.read_json('findings')['metadata']['analysis']
    rows = coverage['files']
    states = {Path(row['path']).name: (row['status'], row['compile_context'], row['error_count'])
              for row in rows}
    if case == 'source-free':
        assert not rows
    elif case == 'skipped':
        assert states == {'sample.cpp': ('skipped', 'none', 0)}
    elif case == 'parse-failed':
        status, _, errors = states['sample.cpp']
        assert status == 'partial' and errors > 0
    elif case == 'missing-detector':
        assert states['sample.cpp'][0] == 'analyzed'
        assert 'CPP-MOD-001' not in coverage['enabled_rules']
    elif case == 'unresolved-declared-context':
        assert states == {'sample.cpp': ('analyzed', 'inferred', 0),
                          'covered.cpp': ('analyzed', 'database', 0)}
    elif case == 'declared-empty-database':
        assert states == {'sample.cpp': ('analyzed', 'fallback', 0)}
    assert before == identify(project)
    return {'case': case, 'source': before, 'states': states, 'manifest': fixed.manifest_sha256}


def main():
    cases = ('source-free', 'skipped', 'parse-failed', 'missing-detector',
             'unresolved-declared-context', 'declared-empty-database')
    failures, readbacks = {}, []
    for case in cases:
        try:
            readbacks.append(exercise(case))
        except (AssertionError, ValueError, KeyError) as error:
            failures[case] = repr(error)
    write(out / 'qualification.json', {'cases': readbacks, 'failures': failures})
    print(f'{len(readbacks)} complete installed legacy negative controls, {len(failures)} failures')
    return int(bool(failures))


if __name__ == '__main__':
    sys.exit(main())
