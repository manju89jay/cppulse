#!/usr/bin/env bash
set -euo pipefail
work=/workspace/work
lane="$work/current38-batch12/coverage-continuation"
source="$work/governance-qualification/checkout"
installed="$work/git-scope-qualification/gates/candidate/installed"
python=/workspace/cppulse/.venv/bin/python
out=$1
"$python" -B "$lane/run.py" before "$out"

overall=0
for phase in lcov cobertura import-lcov import-cobertura invalid; do
  phase_dir="$out/$phase"
  mkdir "$phase_dir" "$phase_dir/outside"
  status=0
  "$python" -B "$lane/run.py" "$phase" "$phase_dir" \
    > "$phase_dir/phase.stdout" 2> "$phase_dir/phase.stderr" || status=$?
  printf '%d\n' "$status" > "$phase_dir/phase.exit"
  printf '%s exit %d\n' "$phase" "$status"
  if (( status != 0 )); then tail -30 "$phase_dir/phase.stderr"; overall=$status; fi
done

m5="$out/m5-policy115"
mkdir "$m5" "$m5/outside"
m5_status=0
"$python" -B "$lane/run.py" m5-prepare "$m5" \
  > "$m5/prepare.stdout" 2> "$m5/prepare.stderr" || m5_status=$?
printf '%d\n' "$m5_status" > "$m5/prepare.exit"
if (( m5_status == 0 )); then
  CPPULSE_POLICY115_INPUTS="$m5/policy115-inputs.json" CPPULSE_POLICY_EXPECT_PREFIX115="$installed" \
    "$python" -B -m pytest -q -p no:cacheprovider -o pythonpath= --import-mode=prepend \
    --basetemp "$m5/pytest" --junitxml "$m5/genuine-policy115.xml" \
    "$source/tests/test_policy_public115.py::test_genuine_retained_lcov_public_assess_check_report_and_deviation" \
    > "$m5/pytest.stdout" 2> "$m5/pytest.stderr" || m5_status=$?
  printf '%d\n' "$m5_status" > "$m5/pytest.exit"
  if (( m5_status == 0 )); then
    "$python" -B "$lane/run.py" m5-finish "$m5" \
      > "$m5/finish.stdout" 2> "$m5/finish.stderr" || m5_status=$?
    printf '%d\n' "$m5_status" > "$m5/finish.exit"
  fi
fi
printf '%d\n' "$m5_status" > "$m5/phase.exit"
printf 'm5-policy115 exit %d\n' "$m5_status"
if (( m5_status != 0 )); then
  for log in "$m5"/*.stderr "$m5"/pytest.stdout; do
    if [[ -f "$log" ]]; then tail -22 "$log"; fi
  done
  overall=$m5_status
fi
"$python" -B "$lane/run.py" after "$out"
cmp "$out/custody-before.json" "$out/custody-after.json"
exit "$overall"
