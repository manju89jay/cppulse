"""Path and byte helpers for a fresh package and its subsequently frozen gates."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


BASE = Path(__file__).resolve().parent
WAVE = BASE.parent
CHECKOUT = WAVE / 'checkout'
WORK = WAVE.parent
BASELINE = 'd3a29029e4dbc24812aeedfa45e90051f04c1e7a'
PREVIOUS = WORK / 'attribution-epoch/candidate'
EARLIER = WORK / 'current38-batch06'
B6_DRIVER = EARLIER / 'git01'
B6_RESULT = EARLIER / 'results/git01'
GIT = Path('/usr/bin/git')
GIT_SHA = '356db14e102d68a1a37d8a1ac577dfd678d45d46e92f468bef8b7154e7bfdc60'
EXTENDS = ('tests/test_git_metric_window_scope.py', 'tests/test_git_behavior.py')
RUNTIME = WORK / 'current38-next/criteria/runtime_inventory.py'
RUNTIME_INVENTORY = WORK / 'current38-next/runtime-inventory.json'
IMAGE_PIN = WORK / 'installed-epoch-prep/installed-runtime-image.txt'
DENIAL = WORK / 'historical-proof-bridge/bodies/work/closure-fr3/deny_network.py'
PAYLOAD_VERIFIER = WORK / 'installed-verify/verify_payloads.py'
ADMISSION = WORK / 'source427-current-epoch/admit_epoch.py'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, document):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(document, stream, indent=2, allow_nan=False)
        stream.write('\n')


def git(*args):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0')
    return subprocess.check_output([GIT, '-C', CHECKOUT, *args], env=env)


def plain(path):
    assert stat.S_ISREG(path.lstat().st_mode), path
    return path


def file_map(root):
    result = {}
    for path in sorted(root.rglob('*')):
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        plain(path)
        result[path.relative_to(root).as_posix()] = {'sha256': sha(path), 'size_bytes': path.stat().st_size}
    return result


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def owned(path):
    actual = path.resolve()
    assert actual.is_relative_to(BASE) and actual != BASE, actual
    return actual


def verify_pins(registration):
    for name, expected in registration['file_sha256'].items():
        assert sha(plain(Path(name))) == expected, name
