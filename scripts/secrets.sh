#!/usr/bin/env bash
set -Eeuo pipefail
mkdir -p reports
docker run --rm --user "$(id -u):$(id -g)" \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/repo \
  -v "$PWD:/repo" -w /repo \
  zricethezav/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f \
  git --log-opts=--all --redact --report-format json --report-path reports/gitleaks-history.json .
# Scan the working tree as well: uncommitted changes and generated files must not leak.
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD:/repo" -w /repo \
  zricethezav/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f \
  dir --redact --report-format json --report-path reports/gitleaks-tree.json .
