#!/usr/bin/env bash
set -euo pipefail

work=/workspace/work
base="$work/git-scope-qualification/gates"
source="$work/git-scope-qualification/checkout"
root=/workspace/cppulse
venv=/workspace/verification-python-venv
python="$venv/bin/python"
runtime=/opt/codex/runtimes/codex-primary-runtime/dependencies/python
image=$(cat "$work/installed-epoch-prep/installed-runtime-image.txt")
denial="$work/historical-proof-bridge/bodies/work/closure-fr3/deny_network.py"
group=$1
freeze=$2
out=$(realpath -m "$3")
[[ "$out" == "$base/"* && -d "$out" ]]
case "$group" in
    package)
        pythonpath=
        args=("$base/package.py" "$freeze" "$out") ;;
    git-public|git-installed|git-source)
        installed=$(python -B - "$freeze" <<'PY'
import json
from pathlib import Path
import sys
registration = json.loads(Path(sys.argv[1]).read_bytes())
assert registration['phase'] == 'tests'
manifest = json.loads(Path(registration['candidate_manifest']).read_bytes())
assert manifest['candidate_tree'] == registration['candidate_tree']
print(manifest['installed'])
PY
)
        case "$group" in
            git-public) pythonpath="$installed" ;;
            git-installed) pythonpath="$installed:$source/tests" ;;
            git-source) pythonpath="$source/python:$source/tests" ;;
        esac
        args=("$base/git_checks.py" "$group" "$freeze" "$out") ;;
    *) exit 2 ;;
esac
mkdir "$out/outside"

exec env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
    docker --host=unix:///var/run/docker.sock run --rm --read-only --network none --user 1000:1000 \
    --tmpfs /home/agent:rw,uid=1000,gid=1000,mode=0700 --tmpfs /tmp:rw,mode=1777 \
    --cap-drop ALL --security-opt no-new-privileges \
    --mount type=bind,src=/usr,dst=/usr,readonly \
    --mount type=bind,src=/etc/alternatives,dst=/etc/alternatives,readonly \
    --mount "type=bind,src=$runtime,dst=$runtime,readonly" \
    --mount "type=bind,src=$root/.venv,dst=$venv,readonly" \
    --mount "type=bind,src=$work,dst=$work,readonly" \
    --mount "type=bind,src=$out,dst=$out" --workdir "$out/outside" \
    --env "PATH=$venv/bin:/usr/bin:/bin" --env LANG=C.UTF-8 \
    --env PYTHONNOUSERSITE=1 --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
    --env "PYTHONPATH=$pythonpath" --env PIP_NO_INDEX=1 --env PIP_NO_CACHE_DIR=1 \
    --env PIP_DISABLE_PIP_VERSION_CHECK=1 --env PIP_CONFIG_FILE=/dev/null \
    --env GIT_CONFIG_GLOBAL=/dev/null --env GIT_CONFIG_NOSYSTEM=1 --env GIT_OPTIONAL_LOCKS=0 \
    "$image" "$python" -B "$denial" "$out/network-denial.json" "$python" -B "${args[@]}"
