#!/usr/bin/env bash
set -Eeuo pipefail
mode=${1:?Usage: trivy.sh image|fs TARGET REPORT}
target=${2:?Missing scan target}
report=${3:?Missing report path}
case "$mode" in image|fs) ;; *) exit 1 ;; esac
severity=$(python3 -c 'import json; print(",".join(json.load(open(".ci/policy.json"))["security"]["blocked_severities"]))')
ignore_unfixed=$(python3 -c 'import json; print(str(json.load(open(".ci/policy.json"))["security"]["ignore_unfixed"]).lower())')
mkdir -p "$(dirname "$report")"
# Development dependency discovery applies to source manifests, not images.
mode_options=()
if [[ "$mode" == fs ]]; then
  mode_options+=(--include-dev-deps)
fi
trivy "$mode" "${mode_options[@]}" --scanners vuln --severity "$severity" --ignore-unfixed="$ignore_unfixed" \
  --exit-code 1 --format json --output "$report" \
  --skip-dirs '**/node_modules,**/.yarn,**/dist,**/coverage,.ci-images,.git' "$target"
