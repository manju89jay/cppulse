#!/usr/bin/env bash
set -euo pipefail
work=/workspace/work
lane="$work/current38-batch14/evidence-imports"
source="$work/governance-qualification/checkout"
installed="$work/git-scope-qualification/gates/candidate/installed"
runtime=/opt/codex/runtimes/codex-primary-runtime/dependencies/python
venv=/workspace/verification-python-venv
actual_venv=/workspace/cppulse/.venv
python="$venv/bin/python"
image=$(cat "$work/installed-epoch-prep/installed-runtime-image.txt")
inventory="$work/current38-next/criteria/runtime_inventory.py"
denial="$work/historical-proof-bridge/bodies/work/closure-fr3/deny_network.py"
out=$(realpath -m "$1")
[[ "$out" == "$work/current38-batch14/"* ]]
mkdir "$out" "$out/outside"
python3 -B "$inventory" check "$out/runtime-before.json"
status=0
env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
  docker --host=unix:///var/run/docker.sock run --rm --read-only --network none --user 1000:1000 \
  --tmpfs /home/agent:rw,uid=1000,gid=1000,mode=0700 --tmpfs /tmp:rw,mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount type=bind,src=/usr,dst=/usr,readonly \
  --mount type=bind,src=/etc/alternatives,dst=/etc/alternatives,readonly \
  --mount "type=bind,src=$runtime,dst=$runtime,readonly" \
  --mount "type=bind,src=$actual_venv,dst=$actual_venv,readonly" \
  --mount "type=bind,src=$actual_venv,dst=$venv,readonly" \
  --mount "type=bind,src=$work,dst=$work,readonly" \
  --mount "type=bind,src=$out,dst=$out" --workdir "$out/outside" \
  --env "PATH=$installed/bin:$venv/bin:/usr/bin:/bin" --env LANG=C.UTF-8 \
  --env PYTHONNOUSERSITE=1 --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
  --env "PYTHONPATH=$installed:$source" --env "CPPULSE_EVIDENCE_EXPECT_PREFIX116=$installed" \
  "$image" "$python" -B "$denial" "$out/network-denial.json" \
  "$python" -B "$lane/observe.py" "$out" > "$out/observe.log" 2>&1 || status=$?
printf '%d\n' "$status" > "$out/observe.exit"
python3 -B "$inventory" check "$out/runtime-after.json"
cmp "$out/runtime-before.json" "$out/runtime-after.json"
tail -14 "$out/observe.log"
exit "$status"
