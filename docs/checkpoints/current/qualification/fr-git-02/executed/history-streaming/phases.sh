#!/usr/bin/env bash
set -euo pipefail
base=/workspace/work/current38-batch11/history-streaming
source=/workspace/work/git-scope-qualification/checkout
python=/workspace/cppulse/.venv/bin/python
out=$1
installed_exit=0
"$python" -B "$base/run.py" "$out" > "$out/installed.stdout" 2> "$out/installed.stderr" || installed_exit=$?
printf '%d\n' "$installed_exit" > "$out/installed.exit"
if (( installed_exit != 0 )); then tail -35 "$out/installed.stderr"; fi
source_exit=0
PYTHONPATH="$source/python" "$python" -B -c '
from pathlib import Path
import sys
from xml.etree import ElementTree
import cppulse
import pytest

source, output = map(Path, sys.argv[1:3])
assert Path(cppulse.__file__).resolve().is_relative_to(source / "python/cppulse")
exit_code = pytest.main(sys.argv[3:])
if not exit_code:
    suites = ElementTree.parse(output).getroot().findall("testsuite")
    assert sum(int(node.get("tests")) for node in suites) == 4
    assert all(int(node.get(status, "0")) == 0 for node in suites for status in ("errors", "failures", "skipped"))
raise SystemExit(exit_code)
' "$source" "$out/original-history.xml" -q -p no:cacheprovider -o pythonpath= --import-mode=prepend \
  --basetemp "$out/pytest" --junitxml "$out/original-history.xml" \
  "$source/tests/test_git_history_cache.py::test_cold_warm_and_append_reuse_one_checked_stream_with_clean_equality" \
  "$source/tests/test_git_history_cache.py::test_pipeline_shared_scan_is_not_repeated_by_silo_szz_or_metadata" \
  "$source/tests/test_git_history_cache.py::test_bounds_are_explicit_and_expanding_scope_matches_clean" \
  "$source/tests/test_git_history_cache.py::test_raw_byte_cap_is_incomplete_and_is_never_a_warm_positive_hit" \
  > "$out/source.stdout" 2> "$out/source.stderr" || source_exit=$?
printf '%d\n' "$source_exit" > "$out/source.exit"
tail -12 "$out/source.stdout"
if (( source_exit != 0 )); then tail -15 "$out/source.stderr"; fi
test "$installed_exit" -eq 0
exit "$source_exit"
