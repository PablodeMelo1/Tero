#!/usr/bin/env bash
set -Eeuo pipefail
mkdir -p reports
image=bridgecrew/checkov:latest@sha256:ece5efac4443084ca273072909985dce988a81e8cc94faa305aeda0df27c68f9
scan() {
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$PWD:/src" -w /src "$image" "$@"
}
# Require health checks, a non-root runtime user and versioned base images.
scan --directory src --framework dockerfile --check CKV_DOCKER_2,CKV_DOCKER_3,CKV_DOCKER_7 \
  --compact --quiet --output json > reports/checkov-docker.json
if find . -path './.git' -prune -o -path '*/node_modules' -prune -o -path '*/.terraform' -prune -o -name '*.tf' -print | grep -q .; then
  scan --directory . --framework terraform --skip-path node_modules --skip-path .terraform \
    --compact --quiet --output json > reports/checkov-terraform.json
fi
