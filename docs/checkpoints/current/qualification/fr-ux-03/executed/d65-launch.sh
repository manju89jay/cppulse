#!/usr/bin/env bash
set -euo pipefail
work=/workspace/work
base="$work/roadmap-order-qualification/legacy-refresh"
source="$work/roadmap-order-qualification/checkout"
candidate="$work/roadmap-order-qualification/gates-final/candidate-retry"
installed="$candidate/installed"
original="$work/git-scope-qualification/legacy-gates"
prefix="$work/attribution-epoch/installed/native/cppulse-native-0.2.0.dev2-linux-x86_64"
runtime=/opt/codex/runtimes/codex-primary-runtime/dependencies/python
venv=/workspace/verification-python-venv
python="$venv/bin/python"
image=$(cat "$work/installed-epoch-prep/installed-runtime-image.txt")
denial="$work/historical-proof-bridge/bodies/work/closure-fr3/deny_network.py"
inventory="$work/current38-next/criteria/runtime_inventory.py"
out=$(realpath -m "$1")
[[ "$out" == "$base/"* ]]
mkdir "$out"
python3 -B "$inventory" check "$out/runtime-before.json"
overall=0
for phase in original-nine native-negatives source-archive installed-archive; do
  result="$out/$phase"
  mkdir "$result" "$result/outside"
  search="$installed"
  console_path="$installed/bin:"
  runner=("$original/$phase.py" "$result" "$candidate")
  if [[ "$phase" == *-archive ]]; then
    origin=${phase%-archive}
    if [[ "$origin" == source ]]; then
      search="$source/python"
      console_path=""
    fi
    search="$search:$source"
    runner=("$base/archive-checks.py" "$base/lane-inputs.json" "$origin" "$result")
  fi
  status=0
  env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
    docker --host=unix:///var/run/docker.sock run --rm --read-only --network none --user 1000:1000 \
      --tmpfs /home/agent:rw,uid=1000,gid=1000,mode=0700 --tmpfs /tmp:rw,mode=1777 \
      --cap-drop ALL --security-opt no-new-privileges \
      --mount type=bind,src=/usr,dst=/usr,readonly \
      --mount type=bind,src=/etc/alternatives,dst=/etc/alternatives,readonly \
      --mount "type=bind,src=$runtime,dst=$runtime,readonly" \
      --mount "type=bind,src=/workspace/cppulse/.venv,dst=$venv,readonly" \
      --mount "type=bind,src=$work,dst=$work,readonly" \
      --mount "type=bind,src=$result,dst=$result" --workdir /tmp \
      --env "PATH=${console_path}$venv/bin:/usr/bin:/bin" --env LANG=C.UTF-8 --env LC_ALL=C.UTF-8 \
      --env PYTHONNOUSERSITE=1 --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
      --env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 --env "PYTHONPATH=$search" --env "CPPULSE_NATIVE_PREFIX=$prefix" \
      --env GIT_CONFIG_GLOBAL=/dev/null --env GIT_CONFIG_NOSYSTEM=1 \
      "$image" "$python" -B "$denial" "$result/network-denial.json" \
      "$python" -B "${runner[@]}" > "$out/$phase.log" 2>&1 || status=$?
  printf '%d\n' "$status" > "$out/$phase.exit"
  printf '%s exit %d\n' "$phase" "$status"
  tail -8 "$out/$phase.log"
  if (( status != 0 )); then overall=$status; fi
done
python3 -B "$inventory" check "$out/runtime-after.json"
cmp "$out/runtime-before.json" "$out/runtime-after.json"
exit "$overall"
