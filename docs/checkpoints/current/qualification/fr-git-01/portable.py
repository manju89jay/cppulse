"""Run the approved FR-GIT-01 assertions with an externally frozen local runtime."""

import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import stat
import subprocess
import sys
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parent
APPROVED = ROOT / 'approved'
TEST_IDS = [
    'tests/test_git_metric_window_scope.py::test_configured_behavior_windows_disclose_unfiltered_legacy_scope',
    'tests/test_git_behavior.py::test_optional_miner_document_preserves_original_output_and_reuses_one_scan',
]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def checked(path, expected):
    path = Path(path)
    assert path.is_absolute() and stat.S_ISREG(path.lstat().st_mode), path
    assert re.fullmatch(r'[0-9a-f]{64}', expected) and sha(path) == expected, path
    return path


def approved_texts():
    assertions = read(ROOT / 'approved-texts.json')
    assert len(assertions['approved_texts']) == 9
    for item in assertions['approved_texts']:
        path = checked(ROOT / item['path'], item['sha256'])
        assert path.stat().st_size == item['size_bytes']
    return assertions


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def original_assertions(git, checkout):
    fixture = load('fixture', APPROVED / 'fixture/fixture.py')
    fixture.GIT = git
    inherited = load('recheck', APPROVED / 'fixture/recheck.py')
    original_path = sys.path.copy()
    try:
        load('common', APPROVED / 'current/common.py')
        current = load('approved_current_git_assertions', APPROVED / 'current/git_checks.py')
    finally:
        sys.path[:] = original_path
    current.CHECKOUT = checkout
    return fixture, inherited, current


def checkout_tree(reg, git):
    checkout = Path(reg['source_root'])
    assert checkout.is_absolute() and checkout.is_dir()
    tree = reg['candidate_tree']
    assert re.fullmatch(r'[0-9a-f]{40}', tree)
    assert subprocess.check_output([git, '-C', checkout, 'cat-file', '-t', tree]).strip() == b'tree'
    assert not subprocess.check_output([git, '-C', checkout, 'ls-files', '-z', '--others'])
    listed = subprocess.check_output([git, '-C', checkout, 'ls-tree', '-rz', '--full-tree', tree])
    entries = {}
    for row in listed.split(b'\0'):
        if not row:
            continue
        descriptor, filename = row.split(b'\t', 1)
        mode, kind, oid = descriptor.split()
        path = checkout / filename.decode('utf-8')
        assert kind == b'blob' and mode in (b'100644', b'100755'), path
        assert path.is_relative_to(checkout) and '..' not in path.relative_to(checkout).parts, path
        info = path.lstat()
        body = path.read_bytes()
        assert stat.S_ISREG(info.st_mode) and bool(info.st_mode & stat.S_IXUSR) == (mode == b'100755'), path
        assert hashlib.sha1(f'blob {len(body)}\0'.encode() + body, usedforsecurity=False).hexdigest() == oid.decode(), path
        entries[filename.decode()] = hashlib.sha256(body).hexdigest()
    assert entries
    for test in TEST_IDS:
        name = Path(test.split('::')[0]).name
        approved = APPROVED / 'tests' / name
        assert sha(approved) == entries['tests/' + name]
    return checkout, entries


def candidate(reg, source_entries):
    path = checked(reg['candidate_manifest'], reg['candidate_manifest_sha256'])
    artifact = read(path)
    assert artifact['candidate_tree'] == reg['tested_runtime_product_tree']
    assert artifact['wheel_sha256'] == reg['wheel_sha256']
    wheel = checked(artifact['wheel'], reg['wheel_sha256'])
    installed = Path(artifact['installed'])
    assert installed.is_absolute() and installed.is_dir() and not installed.is_symlink()
    files = {}
    for path in installed.rglob('*'):
        metadata = path.lstat()
        if not stat.S_ISDIR(metadata.st_mode):
            assert stat.S_ISREG(metadata.st_mode), path
            files[path.relative_to(installed).as_posix()] = {'sha256': sha(path), 'size_bytes': metadata.st_size}
    assert files == artifact['installed_files']
    pins = artifact['namespace_payloads']
    with ZipFile(wheel) as archive:
        names = [name for name in archive.namelist() if name.startswith('cppulse/') and not name.endswith('/')]
        assert len(names) == len(set(names)) and set(names) == {'cppulse/' + name for name in pins}
        assert set(names) == {name for name in files if name.startswith('cppulse/')}
        for name in names:
            relative = name.removeprefix('cppulse/')
            body = archive.read(name)
            digest = hashlib.sha256(body).hexdigest()
            assert pins[relative] == files[name] == {'sha256': digest, 'size_bytes': len(body)}
            if not relative.startswith('data/dashboard/'):
                assert source_entries['python/' + name] == digest
    return artifact


def runtime_probe(reg, out):
    bound = reg['runtime']
    assert Path.cwd() == out / 'outside'
    assert Path(sys.prefix) == Path(bound['venv']['mount'])
    assert Path(sys.executable) == Path(bound['interpreter'])
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    assert home == Path.home() == Path(bound['account_home']) and not any(home.iterdir())
    assert os.getuid() == bound['uid'] and os.getgid() == bound['gid']
    assert {path.name for path in Path('/sys/class/net').iterdir()} == {'lo'}
    denied = {}
    for family in (socket.AF_INET, socket.AF_INET6, socket.AF_UNIX):
        try:
            with socket.socket(family):
                raise AssertionError(f'Socket unexpectedly available: {family.name}')
        except OSError as failure:
            assert failure.errno == errno.ENETUNREACH and failure.errno == bound['denied_errno']
            denied[family.name] = failure.errno
    write(out / 'boundary.json', {'socket_denial': denied, 'account_home': str(home),
                                 'empty_account_home': True, 'cwd': str(Path.cwd()),
                                 'interpreter': str(Path(sys.executable))})


def worker(reg_path, anchor, candidate_anchor, group, out):
    reg = read(checked(reg_path, anchor))
    assert reg['phase'] == 'tests' and reg['candidate_manifest_sha256'] == candidate_anchor
    assert reg['test_nodeids'] == TEST_IDS
    assert reg['original_eight_registration'] == str(APPROVED / 'fixture/fixture.json')
    approved_texts()
    git = checked(reg['runtime']['git'], reg['runtime']['git_sha256'])
    resolved_git = shutil.which('git')
    assert resolved_git and Path(resolved_git).resolve() == git.resolve()
    runtime_probe(reg, out)
    checkout, entries = checkout_tree(reg, git)
    artifact = candidate(reg, entries)
    fixture, inherited, current = original_assertions(git, checkout)
    if group == 'git-source':
        package = checkout / 'python'
        root = 'python/cppulse/'
        origins = {name.removeprefix(root): digest for name, digest in entries.items() if name.startswith(root)}
    else:
        package = Path(artifact['installed'])
        origins = {name: info['sha256'] for name, info in artifact['namespace_payloads'].items()}
    assert os.environ['PYTHONPATH'].split(os.pathsep)[0] == str(package)
    import cppulse.git_miner.main

    write(out / 'qualification-inputs.json', {'source_tree': reg['candidate_tree'],
          'runtime_product_tree': reg['tested_runtime_product_tree'], 'wheel_sha256': reg['wheel_sha256'],
          'source_registration_sha256': anchor, 'candidate_manifest_sha256': candidate_anchor,
          'module_origins': current.modules(package, origins)})
    if group != 'git-public':
        return current.regressions(out, reg, package, origins)

    spec = read(reg['original_eight_registration'])
    assert len(spec['cases']) == 8
    objects = fixture.declare(spec)
    body = (json.dumps(objects, indent=2, allow_nan=False) + '\n').encode()
    actual = hashlib.sha256(body).hexdigest()
    assert actual == reg['fixture_declaration_sha256']
    directory = Path(reg['fixture_dir'])
    assert directory == out / 'fixtures'
    directory.mkdir()
    before = fixture.materialize(directory, objects, spec['expected']['shallow_depth'])
    assert before == fixture.inventory(directory, objects)
    write(out / 'repository-before.json', before)
    for case in spec['cases']:
        inherited.call(out, directory, case, spec['cutoff'])
    after = fixture.inventory(directory, objects)
    write(out / 'repository-after.json', after)
    summaries, failures = inherited.verify_shapes(out, spec, before)
    try:
        extended = current.verify_extended(out, spec)
    except (AssertionError, KeyError, OSError, ValueError) as failure:
        extended = {}
        failures.append({'case': 'extended-scope-parity', 'detail': f'{type(failure).__name__}: {failure}'})
    assert len(summaries) == 8
    if before != after:
        failures.append({'case': 'fixture-stability', 'detail': 'Newly generated local Git inputs changed'})
    write(out / 'qualification.json', {'criterion': 'FR-GIT-01', 'status': 'failed' if failures else 'passed',
          'source_tree': reg['candidate_tree'], 'runtime_product_tree': reg['tested_runtime_product_tree'],
          'wheel_sha256': reg['wheel_sha256'], 'fixture_declaration_sha256': actual,
          'fresh_fixture_generated': True, 'fixture_unchanged': before == after,
          'original_eight_cases': summaries, 'nonpassing': failures, 'additional_scope_predicates': extended,
          'module_origins': current.modules(package, origins)})
    return int(bool(failures))


if __name__ == '__main__':
    if sys.flags.optimize:
        raise SystemExit('Run qualification with Python assertions enabled.')
    reg, sha_reg, sha_candidate, group, out = sys.argv[1:]
    assert group in ('git-public', 'git-source', 'git-installed')
    sys.exit(worker(Path(reg), sha_reg, sha_candidate, group, Path(out)))
