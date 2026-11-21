#!/usr/bin/env bash
set -euo pipefail
work=/workspace/work
base="$work/current38-batch14"
lane="$base/no-false-followup"
candidate="$work/git-scope-qualification/gates/candidate"
root=/workspace/cppulse
installed="$candidate/installed"
runtime=/opt/codex/runtimes/codex-primary-runtime/dependencies/python
python="$root/.venv/bin/python"
denial="$work/historical-proof-bridge/bodies/work/closure-fr3/deny_network.py"
out=$1
[[ "$out" == "$base/no-false-followup-"* ]]
mkdir "$out" "$out/outside"
image=$(cat "$work/installed-epoch-prep/installed-runtime-image.txt")
env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
  docker --host=unix:///var/run/docker.sock run --rm --read-only --network none --user 1000:1000 \
  --tmpfs /home/agent:rw,uid=1000,gid=1000,mode=0700 --tmpfs /tmp:rw,mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount type=bind,src=/usr,dst=/usr,readonly \
  --mount type=bind,src=/etc/alternatives,dst=/etc/alternatives,readonly \
  --mount "type=bind,src=$runtime,dst=$runtime,readonly" \
  --mount "type=bind,src=$work/current38-next/public-flow/repo-alias,dst=$root,readonly" \
  --mount "type=bind,src=$root/.venv,dst=$root/.venv,readonly" \
  --mount "type=bind,src=$root/.venv,dst=/workspace/verification-python-venv,readonly" \
  --mount "type=bind,src=$work,dst=$work,readonly" \
  --mount "type=bind,src=$out,dst=$out" --workdir "$out/outside" \
  --env "PATH=$installed/bin:$root/.venv/bin:/usr/bin:/bin" --env LANG=C.UTF-8 \
  --env PYTHONNOUSERSITE=1 --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
  --env "PYTHONPATH=$installed" --env GIT_CONFIG_GLOBAL=/dev/null --env GIT_CONFIG_NOSYSTEM=1 \
  "$image" "$python" -B "$denial" "$out/network-denial.json" \
  /usr/bin/bash "$lane/phases.sh" "$out"
