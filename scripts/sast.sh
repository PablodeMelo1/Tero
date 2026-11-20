#!/usr/bin/env bash
set -Eeuo pipefail
mkdir -p reports
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e SEMGREP_SEND_METRICS=off -e SEMGREP_ENABLE_VERSION_CHECK=0 \
  -v "$PWD:/src" -w /src \
  semgrep/semgrep:1.182.0@sha256:4a34048c04fef049f71665047f074cffb00cc3d89482f965a5cd151d589237af \
  semgrep scan --config .semgrep.yml --error --strict --metrics=off \
    --json-output reports/semgrep.json --exclude '**/.yarn/**' src
