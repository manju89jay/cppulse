#!/usr/bin/env bash
set -euo pipefail
lane=/workspace/work/current38-batch12/coverage-import-retry
python=/workspace/cppulse/.venv/bin/python
out=$1
"$python" -B "$lane/run.py" before "$out"
overall=0
for adapter in lcov cobertura; do
  phase="$out/import-$adapter"
  mkdir "$phase" "$phase/outside"
  status=0
  "$python" -B "$lane/run.py" "$adapter" "$phase" > "$phase/phase.stdout" 2> "$phase/phase.stderr" || status=$?
  printf '%d\n' "$status" > "$phase/phase.exit"
  printf 'import-%s exit %d\n' "$adapter" "$status"
  if (( status != 0 )); then tail -30 "$phase/phase.stderr"; overall=$status; fi
done
"$python" -B "$lane/run.py" after "$out"
cmp "$out/custody-before.json" "$out/custody-after.json"
exit "$overall"
