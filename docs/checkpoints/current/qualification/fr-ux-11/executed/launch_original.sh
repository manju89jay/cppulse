#!/usr/bin/env bash
set -euo pipefail
work=/workspace/work
base="$work/current38-next"
current="$work/attribution-epoch"
source="$current/checkout"
installed="$current/candidate/installed"
sysroot="$work/toolchain/sysroot"
llvm="$sysroot/usr"
venv=/workspace/verification-python-venv
python="$venv/bin/python"
runtime=/opt/codex/runtimes/codex-primary-runtime/dependencies/python
denial="$work/historical-proof-bridge/bodies/work/closure-fr3/deny_network.py"
image=$(cat "$work/installed-epoch-prep/installed-runtime-image.txt")
group=$1
out="$base/results/$group"
mkdir "$out" "$out/outside" "$out/privacy-fixtures"
package="$installed"
if [[ "$group" == privacy-source ]]; then package="$source/python"; fi
exec env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
  docker --host=unix:///var/run/docker.sock run --rm --read-only --network none --user 1000:1000 \
  --tmpfs /home/agent:rw,uid=1000,gid=1000,mode=0700 --tmpfs /tmp:rw,mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges \
  --mount type=bind,src=/usr,dst=/usr,readonly \
  --mount type=bind,src=/etc/alternatives,dst=/etc/alternatives,readonly \
  --mount "type=bind,src=$runtime,dst=$runtime,readonly" \
  --mount "type=bind,src=/workspace/cppulse/.venv,dst=$venv,readonly" \
  --mount "type=bind,src=$source,dst=$source,readonly" \
  --mount "type=bind,src=$installed,dst=$installed,readonly" \
  --mount "type=bind,src=$sysroot,dst=$sysroot,readonly" \
  --mount "type=bind,src=$base/criteria,dst=$base/criteria,readonly" \
  --mount "type=bind,src=$denial,dst=$denial,readonly" \
  --mount "type=bind,src=$out,dst=$out" --workdir "$out/outside" \
  --env "PATH=$venv/bin:/usr/bin:/bin" --env LANG=C.UTF-8 --env PYTHONNOUSERSITE=1 \
  --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
  --env "PYTHONPATH=$package:$source/tests:$source" --env "CPPULSE_GATE_PACKAGE=$package" \
  --env "CPPULSE_EXTENSION_CLANG_INCLUDE=$llvm/lib/llvm-19/include" \
  --env "CPPULSE_EXTENSION_LIBCLANG=$llvm/lib/x86_64-linux-gnu/libclang-19.so.19" \
  --env "CPPULSE_EXTENSION_QUALIFIED_PREFIX=$installed" --env "CPPULSE_EXTENSION_EVIDENCE_DIR=$out/extension" \
  --env "LD_LIBRARY_PATH=$llvm/lib/x86_64-linux-gnu" \
  --env "CPPULSE_DIAGNOSTIC_EXPECT_PREFIX112=$package" --env "CPPULSE_PRIVACY_FIXTURES112=$out/privacy-fixtures" \
  "$image" "$python" -B "$denial" "$out/network-denial.json" "$python" -B \
  "$base/criteria/run_original.py" "$group" "$out" "$source"
