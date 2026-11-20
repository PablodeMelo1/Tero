#!/usr/bin/env bash
set -Eeuo pipefail
environment=${1:?Usage: rollback.sh dev|test|prod ROOT_DIR}
root=${2:?Missing root}
target=$(readlink -f "$root/previous")
[[ -f "$target/manifest.json" ]] || { echo 'No previous release' >&2; exit 1; }
cd "$target"
RELEASE_SHA=$(python3 -c 'import json; print(json.load(open("manifest.json"))["commit"])')
export RELEASE_SHA
bash scripts/deploy.sh "$environment" "$root"
