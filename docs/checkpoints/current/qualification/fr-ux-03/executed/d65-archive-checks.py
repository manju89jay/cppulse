"""Run the existing five archive assertions on each d65 package origin."""
from collections import Counter
import errno
import hashlib
import json
import os
from pathlib import Path
import pwd
import socket
import sys
import xml.etree.ElementTree as ET

import pytest


pins_path, phase, output_path = sys.argv[1:]
pins = json.loads(Path(pins_path).read_bytes())
source = Path(pins["source_root"])
package = {"source": source / "python", "installed": Path(pins["installed_root"])}[phase]
output = Path(output_path)
assert Path.cwd() == Path('/tmp')
os.chdir(output / "outside")
home = Path(pwd.getpwuid(os.getuid()).pw_dir)
assert home == Path.home() == Path('/home/agent') and not any(home.iterdir())
assert os.environ['PYTHONPATH'].split(os.pathsep) == [str(package), str(source)]
assert set(entry.name for entry in Path('/sys/class/net').iterdir()) == {'lo'}
for family in (socket.AF_INET, socket.AF_INET6, socket.AF_UNIX):
    try:
        with socket.socket(family):
            pass
    except OSError as error:
        assert error.errno == errno.ENETUNREACH, error
    else:
        raise AssertionError(f'Unexpected socket family access {family.name}')

import cppulse
from cppulse import importer, run_store
from scripts import import_pipeline_run


assert import_pipeline_run.import_pipeline is importer.import_pipeline
assert import_pipeline_run.main is importer.main


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def origins():
    result = {}
    for name, module in sorted(sys.modules.items()):
        if name != 'cppulse' and not name.startswith('cppulse.'):
            continue
        path = Path(module.__file__).resolve(strict=True)
        assert path.is_relative_to(package / 'cppulse'), (name, path)
        digest = sha(path)
        assert digest == pins['file_sha256'][str(path)], (name, path)
        result[name] = {'path': str(path), 'sha256': digest}
    return result


before = origins()
shim = Path(import_pipeline_run.__file__).resolve(strict=True)
assert shim == source / 'scripts/import_pipeline_run.py' and sha(shim) == pins['file_sha256'][str(shim)]
assert {cppulse.__name__, importer.__name__, run_store.__name__} <= before.keys()
xml = output / 'qualification.xml'
selectors = pins['archive_test_selectors']
status = pytest.main([
    '-q', '--import-mode=importlib', '-c', '/dev/null', '-p', 'no:cacheprovider',
    f'--rootdir={source}', f'--confcutdir={source / "tests"}',
    f'--basetemp={output / "pytest"}', f'--junitxml={xml}',
    *(str(source / selector) for selector in selectors),
])
after = origins()
assert all(after[name] == value for name, value in before.items())
rows = list(ET.parse(xml).iter('testcase')) if xml.exists() else []
actual = Counter(case.attrib['name'] for case in rows)
nonpasses = {case.attrib['name']: tag for case in rows for tag in ('failure', 'error', 'skipped')
             if case.find(tag) is not None}
with (output / 'qualification.json').open('x', encoding='utf-8') as stream:
    json.dump({'origin': phase, 'selected': selectors, 'actual_exit': int(status), 'cases': actual,
               'nonpasses': nonpasses, 'junit_sha256': sha(xml) if xml.exists() else None,
               'module_origins': after, 'shim': {'path': str(shim), 'sha256': sha(shim)},
               'initial_home_empty': True, 'runtime_working_directory': str(Path.cwd())}, stream, indent=2)
    stream.write('\n')
if status == 0:
    expected = Counter(name.split('::')[1] for name in selectors)
    assert actual == expected and not nonpasses, (actual, nonpasses)
sys.exit(int(status))
