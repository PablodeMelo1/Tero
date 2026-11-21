#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

environment=${1:?Usage: deploy.sh dev|test|prod ROOT_DIR}
root=${2:?Missing deployment root}
case "$environment" in dev|test|prod) ;; *) echo 'Invalid environment' >&2; exit 1 ;; esac
release=$(pwd)
[[ -f "$root/.env" ]] || { echo "Configure $root/.env first" >&2; exit 1; }
mkdir -p "$root" reports
exec 9>"$root/deploy.lock"
flock -w 600 9

python3 scripts/manifest.py "${RELEASE_SHA:?Missing RELEASE_SHA}" > images.env
compose() {
  docker compose --project-name "tero-$environment" --env-file "$root/.env" \
    --env-file "$1/images.env" -f "$1/deploy/compose.yml" "${@:2}"
}
previous=$(readlink -f "$root/current" || true)
restore() {
  status=$?
  trap - ERR
  compose "$release" logs --no-color --tail 200 > reports/compose.log 2>&1 || true
  if [[ -n "$previous" && -f "$previous/images.env" ]]; then
    echo 'Deployment failed; restoring previous images' >&2
    compose "$previous" up -d --no-build --wait --wait-timeout 180 || echo 'ROLLBACK FAILED: inspect the server' >&2
  fi
  exit "$status"
}
trap restore ERR
compose "$release" config --quiet
compose "$release" pull
compose "$release" up -d --no-build --wait --wait-timeout 180
ui_port=$(compose "$release" port ui 8080 | awk -F: '{print $NF}')
admin_port=$(compose "$release" port admin 8080 | awk -F: '{print $NF}')
[[ "$ui_port" =~ ^[0-9]+$ && "$admin_port" =~ ^[0-9]+$ ]]
python3 scripts/smoke.py "http://127.0.0.1:$ui_port" "http://127.0.0.1:$admin_port" | tee reports/smoke.log
if [[ "$environment" == test ]]; then
  python3 scripts/e2e.py "http://127.0.0.1:$ui_port" | tee reports/e2e.log
  bash scripts/zap.sh "http://127.0.0.1:$ui_port" "$release/reports" ui
  bash scripts/zap.sh "http://127.0.0.1:$admin_port" "$release/reports" admin
fi
compose "$release" ps > reports/compose-status.txt
ln -sfn "$release" "$root/current.next"
mv -Tf "$root/current.next" "$root/current"
if [[ -n "$previous" && -f "$previous/images.env" ]]; then
  ln -sfn "$previous" "$root/previous"
fi
echo "$RELEASE_SHA" > "$root/deployed-commit"
echo "Deployed $RELEASE_SHA to $environment"
