#!/usr/bin/env bash
set -euo pipefail
work=/workspace/work
base="$work/git-scope-qualification"
candidate=$(realpath "$1")
out=$(realpath -m "$2")
[[ "$candidate" == "$base/"* && "$out" == "$base/"* ]]
installed="$candidate/installed"
prefix="$work/attribution-epoch/installed/native/cppulse-native-0.2.0.dev2-linux-x86_64"
runtime=/opt/codex/runtimes/codex-primary-runtime/dependencies/python
venv=/workspace/verification-python-venv
python="$venv/bin/python"
image=$(cat "$work/installed-epoch-prep/installed-runtime-image.txt")
denial="$work/historical-proof-bridge/bodies/work/closure-fr3/deny_network.py"
mkdir "$out"
overall=0
for named in original-nine native-negatives source-contracts installed-contracts; do
    status=0
    result="$out/$named"
    mkdir "$result"
    search_path="$installed"
    entry=("$python" -B "$base/legacy-gates/$named.py" "$result" "$candidate")
    if [[ "$named" == source-contracts || "$named" == installed-contracts ]]; then
        origin="$installed"
        if [[ "$named" == source-contracts ]]; then origin="$base/checkout/python"; fi
        search_path="$origin:$base/checkout:$base/checkout/tests"
        entry=(/usr/bin/bash "$base/legacy-gates/pytest-check.sh" "$origin" "$result")
    fi
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
      --env "PATH=$installed/bin:$venv/bin:/usr/bin:/bin" --env LANG=C.UTF-8 \
      --env PYTHONNOUSERSITE=1 --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
      --env "PYTHONPATH=$search_path" --env "CPPULSE_NATIVE_PREFIX=$prefix" \
      --env GIT_CONFIG_GLOBAL=/dev/null --env GIT_CONFIG_NOSYSTEM=1 \
      "$image" "$python" -B "$denial" "$result/network-denial.json" \
      "${entry[@]}" \
      > "$out/$named.log" 2>&1 || status=$?
    printf '%d\n' "$status" > "$out/$named.exit"
    printf '%s exit %d\n' "$named" "$status"
    tail -9 "$out/$named.log"
    if (( status != 0 )); then overall=$status; fi
done
exit "$overall"
