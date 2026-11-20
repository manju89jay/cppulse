"""Installed-style snapshot rendering needs package assets and core libraries only."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

from cppulse.presentation import build_snapshot_view
from test_presentation import publish_snapshot


def test_packaged_view_build_and_html_json_work_outside_checkout_without_extras(
    tmp_path: Path,
) -> None:
    import cppulse

    snapshot = publish_snapshot(tmp_path, legacy=True)
    expected = build_snapshot_view(snapshot)
    expected_path = tmp_path / "expected.json"
    expected_path.write_text(json.dumps(expected))
    package = Path(cppulse.__file__).resolve().parent
    archive = tmp_path / "cppulse-core.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for path in package.rglob("*"):
            if path.is_file() and path.suffix in {
                ".py",
                ".json",
                ".html",
                ".css",
                ".cmake",
            }:
                output.write(path, Path("cppulse") / path.relative_to(package))
    program = r"""
import importlib.abc
import json
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
class BlockExtras(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'fastapi','uvicorn','weasyprint','matplotlib','xgboost','sklearn','shap','numpy','pandas','git'}:
            raise ModuleNotFoundError('Blocked non-render dependency: ' + fullname)
sys.meta_path.insert(0, BlockExtras())
import cppulse
assert '.zip/' in cppulse.__file__, cppulse.__file__
from cppulse.errors import CppulseError
from cppulse.presentation import build_snapshot_view, render_snapshot_json, render_snapshot_html, render_snapshot_pdf
from cppulse.run_store import RunStore
snapshot = RunStore.open_existing(sys.argv[2]).open_run(sys.argv[3], manifest_sha256=sys.argv[4])
view = build_snapshot_view(snapshot)
assert view == json.loads(Path(sys.argv[5]).read_text())
assert json.loads(render_snapshot_json(view)) == view
html = render_snapshot_html(view)
assert 'Recorded verification snapshot' in html
assert 'background:' in html and 'Refactoring Roadmap' in html
try:
    render_snapshot_pdf(view)
except CppulseError as error:
    assert error.code == 'OPTIONAL_DEPENDENCY_MISSING'
else:
    raise AssertionError('PDF cannot claim success without the optional backend')
print('packaged view/HTML/JSON passed without optional or heavy runtime imports')
"""
    environment = {
        key: value
        for key, value in os.environ.items()
        if key != "PYTHONPATH" and not key.startswith(("COV_CORE_", "COVERAGE_"))
    }
    process = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            program,
            str(archive),
            str(snapshot.path.parent.parent),
            snapshot.run_id,
            snapshot.manifest_sha256,
            str(expected_path),
        ],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert "packaged view/HTML/JSON passed" in process.stdout
