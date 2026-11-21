#!/usr/bin/env bash
set -euo pipefail
work=/workspace/work
source="$work/attribution-epoch/checkout"
base="$work/current38-batch07/provenance-v3"
python=/workspace/cppulse/.venv/bin/python
out=$1
status=0
"$python" -B "$base/run.py" "$out" > "$out/mixed.stdout" 2> "$out/mixed.stderr" || status=$?
printf '%d\n' "$status" > "$out/mixed.exit"
if (( status != 0 )); then tail -18 "$out/mixed.stderr"; fi
tests=0
"$python" -B -m pytest -q -p no:cacheprovider --import-mode=prepend \
  --basetemp "$out/pytest" --junitxml "$out/original-transport.xml" \
  "$source/tests/test_evidence_provenance_reporting.py" "$source/tests/test_test_import.py" \
  > "$out/original-transport.log" 2>&1 || tests=$?
printf '%d\n' "$tests" > "$out/original-transport.exit"
tail -12 "$out/original-transport.log"
test "$status" -eq 0
exit "$tests"
