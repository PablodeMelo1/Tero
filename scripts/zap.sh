#!/usr/bin/env bash
set -Eeuo pipefail
target=${1:?Missing target URL}
reports=${2:?Missing absolute reports directory}
name=${3:?Missing report name}
[[ "$name" =~ ^(ui|admin)$ ]]
mkdir -p "$reports"
set +e
docker run --rm --network host --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$reports:/zap/wrk:rw" \
  ghcr.io/zaproxy/zaproxy:stable@sha256:030d3df57735dacbb83464854758e674dd9ad01d79d12a129a8e58b1fd384238 \
  zap-baseline.py -t "$target" -z "-dir /tmp/tero-zap" -I -J "zap-$name.json" -r "zap-$name.html"
status=$?
set -e
if (( status > 2 )); then
  echo "ZAP execution failed (exit $status)" >&2
  exit "$status"
fi
python3 scripts/zap_gate.py < "$reports/zap-$name.json"
