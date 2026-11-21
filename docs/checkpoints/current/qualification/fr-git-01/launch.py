"""Use an externally preregistered existing tests registration for a local run."""

import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

from portable import APPROVED, ROOT, TEST_IDS, approved_texts, checked, read, write


def environment():
    return {name: value for name, value in os.environ.items()
            if name not in ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH')}


def attachments(reg, runtime, reg_path, anchors, output):
    checked(reg_path, anchors[0])
    checked(reg['candidate_manifest'], anchors[1])
    assert reg['candidate_manifest_sha256'] == anchors[1]
    assert reg['phase'] == 'tests' and reg['test_nodeids'] == TEST_IDS
    assert not reg.get('fixture_files'), 'Portable receiving runs preregister a recipe and generate new Git objects.'
    assert reg['original_eight_registration'] == str(APPROVED / 'fixture/fixture.json')
    assert Path(reg['fixture_dir']) == output / 'git-public/fixtures'
    assert re.fullmatch(r'[0-9a-f]{64}', reg['fixture_declaration_sha256'])
    for path, expected in reg['file_sha256'].items():
        checked(path, expected)
    selected = [ROOT / 'approved-texts.json', ROOT / 'portable.py', ROOT / 'launch.py',
                Path(reg['source_root']) / 'tests/test_behavior_identity_history.py',
                Path(reg['candidate_manifest'])]
    selected += [ROOT / row['path'] for row in approved_texts()['approved_texts']]
    for key in ('docker', 'git', 'denier', 'checker', 'inventory', 'host_python'):
        path = checked(runtime[key], runtime[key + '_sha256'])
        assert reg['file_sha256'][str(path)] == runtime[key + '_sha256'], key
    for path in selected:
        assert str(path) in reg['file_sha256'], path
    artifact = read(reg['candidate_manifest'])
    assert reg['file_sha256'][artifact['wheel']] == reg['wheel_sha256'] == artifact['wheel_sha256']
    for name, item in artifact['installed_files'].items():
        path = Path(artifact['installed']) / name
        assert reg['file_sha256'][str(path)] == item['sha256'], path


def literal_mount(path, target=None):
    src, dest = str(path), str(target if target is not None else path)
    for item in (src, dest):
        assert Path(item).is_absolute() and ',' not in item and '\n' not in item
    return ['--mount', f'type=bind,src={src},dst={dest},readonly']


def verify_runtime(runtime, receipt, env):
    checker = Path(runtime['checker'])
    assert checker.parent.parent / 'runtime-inventory.json' == Path(runtime['inventory']), (
        'The selected runtime checker must bind its exact declared inventory')
    subprocess.run([runtime['host_python'], '-E', '-B', checker, 'check', receipt], env=env,
                   capture_output=False, check=True)
    result = read(receipt)
    assert result['manifest_sha256'] == runtime['inventory_sha256']
    assert result['image']['id'] == runtime['image'] and result['entries_verified'] > 0
    return result


def docker_group(reg, runtime, reg_path, anchors, out, group, env):
    artifact = read(reg['candidate_manifest'])
    source = Path(reg['source_root'])
    installed = Path(artifact['installed'])
    wheel = Path(artifact['wheel'])
    package = source / 'python' if group == 'git-source' else installed
    pythonpath = str(package) if group == 'git-public' else os.pathsep.join(map(str, (package, source / 'tests')))
    home = Path(runtime['account_home'])
    interpreter = Path(runtime['interpreter'])
    venv = runtime['venv']
    assert home.is_absolute() and home != Path('/') and ',' not in str(home) and ':' not in str(home)
    assert interpreter.is_relative_to(venv['mount'])
    uid, gid = runtime['uid'], runtime['gid']
    assert isinstance(uid, int) and uid > 0 and isinstance(gid, int) and gid > 0
    out.mkdir()
    (out / 'outside').mkdir()
    command = [runtime['docker'], '--host=' + runtime['docker_host'], 'run', '--rm', '--pull=never',
               '--read-only', '--network', 'none', '--user', f'{uid}:{gid}', '--cap-drop', 'ALL',
               '--security-opt', 'no-new-privileges', '--tmpfs', f'{home}:rw,uid={uid},gid={gid},mode=0700',
               '--tmpfs', '/tmp:rw,mode=1777']
    seen = set()
    for item in [*runtime['mounts'], venv, {'source': str(ROOT), 'mount': str(ROOT)},
                 {'source': str(source), 'mount': str(source)},
                 {'source': str(reg_path), 'mount': str(reg_path)},
                 {'source': runtime['denier'], 'mount': runtime['denier']},
                 {'source': str(installed), 'mount': str(installed)},
                 {'source': str(wheel), 'mount': str(wheel)},
                 {'source': reg['candidate_manifest'], 'mount': reg['candidate_manifest']}]:
        target = item['mount']
        assert target not in seen and Path(target) != Path('/')
        seen.add(target)
        command.extend(literal_mount(item['source'], target))
    assert str(out) not in seen
    command.extend(['--mount', f'type=bind,src={out},dst={out}', '--workdir', str(out / 'outside')])
    for value in (
        'PATH=' + os.pathsep.join((str(interpreter.parent), str(Path(runtime['git']).parent), '/usr/bin', '/bin')),
        'LANG=C.UTF-8', 'PYTHONNOUSERSITE=1', 'PYTHONDONTWRITEBYTECODE=1', 'TMPDIR=/tmp',
        'PYTHONPATH=' + pythonpath, 'GIT_CONFIG_GLOBAL=/dev/null', 'GIT_CONFIG_NOSYSTEM=1',
        'GIT_OPTIONAL_LOCKS=0',
    ):
        command.extend(['--env', value])
    command.extend([runtime['image'], str(interpreter), '-B', runtime['denier'], str(out / 'network-denial.json'),
                    str(interpreter), '-B', str(ROOT / 'portable.py'),
                    str(reg_path), *anchors, group, str(out)])
    with (out / 'process.stdout').open('xb') as stdout, (out / 'process.stderr').open('xb') as stderr:
        run = subprocess.run(command, env=env, stdout=stdout, stderr=stderr)
    write(out / 'process.json', {'argv': command, 'exit_status': run.returncode, 'group': group})
    if run.returncode == 0:
        denial = read(out / 'network-denial.json')
        assert denial['rules'] == ['socket', 'socketpair', 'connect', 'sendto', 'sendmsg', 'sendmmsg']
        assert {(probe['family'], probe['errno']) for probe in denial['probes']} == {
            (1, runtime['denied_errno']), (2, runtime['denied_errno']), (10, runtime['denied_errno'])}
        assert {'NoNewPrivs:\t1', 'Seccomp:\t2'} <= set(denial['proc_status'])
        assert denial['exec'] == command[command.index(runtime['denier']) + 2:]
    return run.returncode


def main(reg_path, anchor, candidate_anchor):
    reg_path = checked(Path(reg_path), anchor)
    reg = read(reg_path)
    runtime = reg['runtime']
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', runtime['image'])
    assert runtime['docker_host'].startswith('unix:///')
    owned = Path(reg['owned_root']).resolve(strict=True)
    assert owned.is_dir() and owned != Path('/') and owned.stat().st_uid == os.getuid()
    output = Path(reg['output'])
    assert output.is_absolute() and output.parent == owned and ',' not in str(output) and '\n' not in str(output)
    anchors = (anchor, candidate_anchor)
    attachments(reg, runtime, reg_path, anchors, output)
    env = environment()
    docker_image = subprocess.check_output([runtime['docker'], '--host=' + runtime['docker_host'],
                                           'image', 'inspect', runtime['image']], env=env)
    image, = json.loads(docker_image)
    assert image['Id'] == runtime['image'] and image['RootFS']['Layers'] == runtime['image_root_layers']
    output.mkdir()
    before = verify_runtime(runtime, output / 'runtime-before.json', env)
    states = {}
    try:
        for group in ('git-public', 'git-source', 'git-installed'):
            states[group] = docker_group(reg, runtime, reg_path, anchors, output / group, group, env)
    finally:
        after = verify_runtime(runtime, output / 'runtime-after.json', env)
        attachments(reg, runtime, reg_path, anchors, output)
        assert before == after
    write(output / 'execution.json', {'source_tree': reg['candidate_tree'],
          'runtime_product_tree': reg['tested_runtime_product_tree'], 'wheel_sha256': reg['wheel_sha256'],
          'registration_sha256': anchor, 'candidate_manifest_sha256': candidate_anchor,
          'runtime_inventory_sha256': runtime['inventory_sha256'], 'actual_exit_statuses': states})
    return int(len(states) != 3 or any(states.values()))


if __name__ == '__main__':
    if sys.flags.optimize:
        raise SystemExit('Run qualification with Python assertions enabled.')
    sys.exit(main(*sys.argv[1:]))
