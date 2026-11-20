#!/usr/bin/env bash
set -Eeuo pipefail
tag=${RELEASE_SHA:-ci}
project="tero-ci-${GITHUB_RUN_ID:-local}"
env_file=$(mktemp)
mkdir -p reports
python3 - "$tag" > "$env_file" <<'PY'
import secrets, sys
for service in ('admin', 'catalog', 'cart', 'checkout', 'orders', 'ui'):
    print(f'IMAGE_{service.upper()}=tero-{service}:{sys.argv[1]}')
for key in ('DB_PASSWORD', 'ADMIN_PASSWORD', 'ADMIN_JWT_SECRET'):
    print(f'{key}={secrets.token_hex(32)}')
print('ADMIN_USERNAME=ci-admin\nUI_PORT=0\nADMIN_PORT=0')
PY
compose() { docker compose -p "$project" --env-file "$env_file" -f deploy/compose.yml "$@"; }
cleanup() {
  status=$?
  trap - EXIT
  compose logs --no-color --tail 200 > reports/integration.log 2>&1 || true
  compose down --volumes --remove-orphans || true
  rm -f "$env_file"
  exit "$status"
}
trap cleanup EXIT
compose pull db redis
compose up -d --no-build --pull never --wait --wait-timeout 240
ui_port=$(compose port ui 8080 | awk -F: '{print $NF}')
admin_port=$(compose port admin 8080 | awk -F: '{print $NF}')
python3 scripts/smoke.py "http://127.0.0.1:$ui_port" "http://127.0.0.1:$admin_port" | tee reports/smoke.log
python3 scripts/e2e.py "http://127.0.0.1:$ui_port" | tee reports/e2e.log

if [[ "${RUN_DAST:-false}" == true ]]; then
  bash scripts/zap.sh "http://127.0.0.1:$ui_port" "$PWD/reports" ui
  bash scripts/zap.sh "http://127.0.0.1:$admin_port" "$PWD/reports" admin
fi
