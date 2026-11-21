#!/usr/bin/env bash
# Regenerate and validate dependency files with the project's container toolchains.
set -Eeuo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
if [[ $# -eq 0 ]]; then
  cat <<'PLAN'
Remediación de dependencias de Tero:
  - Catalog/Orders: actualizar pgx y paquetes golang.org/x afectados.
  - Catalog: actualizar OpenTelemetry, gRPC y compress.
  - Checkout: alinear Nest 11.2.9 y corregir cinco transitivas dentro de su major.
  - Regenerar locks en una copia aislada; ejecutar Go tests, checkout y Trivy.
  - Copiar los seis archivos de dependencias solo si todas las validaciones pasan.
Ejecutar con --apply en un equipo con Python 3, Docker y acceso a los registros.
No realiza commits, push ni cambios en GitHub.
PLAN
  exit 0
fi
[[ $# -eq 1 && $1 == --apply ]] || { echo 'Uso: remediate-dependencies.sh [--apply]' >&2; exit 2; }
command -v python3 >/dev/null
command -v docker >/dev/null
docker info >/dev/null
mkdir -p "$root/.cache"
stage=$(mktemp -d "$root/.cache/dependency-remediation.XXXXXX")
echo "Copia de trabajo y reportes: $stage"
python3 - "$root" "$stage" <<'PY'
import hashlib, json, pathlib, shutil, sys
root, stage = map(pathlib.Path, sys.argv[1:])
files = ['src/catalog/go.mod', 'src/catalog/go.sum', 'src/orders/go.mod',
         'src/orders/go.sum', 'src/checkout/package.json', 'src/checkout/yarn.lock']
snapshot = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}
(stage / 'snapshot.json').write_text(json.dumps(snapshot))
shutil.copytree(root / 'src', stage / 'src', ignore=shutil.ignore_patterns(
    'node_modules', 'dist', 'coverage', 'coverage.out', '__pycache__', '.pytest_cache',
    '.coverage', 'install-state.gz', 'cache', '*.tsbuildinfo'))
shutil.copytree(root / '.ci', stage / '.ci')
(stage / 'reports').mkdir()
package = stage / 'src/checkout/package.json'
data = json.loads(package.read_text())
for name in ('@nestjs/common', '@nestjs/core', '@nestjs/platform-express'):
    data['dependencies'][name] = '11.2.9'
data.setdefault('resolutions', {}).update({
    'body-parser': '2.4.0', 'js-yaml': '4.3.2', 'lodash': '4.18.1', 'proxy-addr': '2.0.8',
    'path-to-regexp': '8.4.2',
})
package.write_text(json.dumps(data, indent=2) + '\n')
PY
node_image=$(awk 'NR==1 {print $2}' "$root/src/checkout/Dockerfile")
go_image=$(awk 'NR==1 {print $2}' "$root/src/catalog/Dockerfile")
[[ "$go_image" == "$(awk 'NR==1 {print $2}' "$root/src/orders/Dockerfile")" ]] || {
  echo 'Catalog y Orders deben usar el mismo toolchain Go.' >&2; exit 1;
}
container() {
  local service=$1 image=$2
  shift 2
  docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
    -v "$stage:/work" -w "/work/src/$service" -e HOME=/tmp \
    -e GOPATH=/tmp/go -e GOCACHE=/tmp/go-build -e GOTOOLCHAIN=local \
    -e YARN_ENABLE_SCRIPTS=false -e YARN_ENABLE_IMMUTABLE_INSTALLS=false \
    "$image" "$@"
}
common_go=(github.com/jackc/pgx/v5@v5.9.0 golang.org/x/net@v0.62.0 \
  golang.org/x/crypto@v0.58.0 golang.org/x/text@v0.43.0)
catalog_go=(github.com/klauspost/compress@v1.18.7 go.opentelemetry.io/otel@v1.47.0 \
  go.opentelemetry.io/otel/sdk@v1.47.0 go.opentelemetry.io/otel/exporters/otlp/otlptrace@v1.47.0 \
  go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp@v1.47.0 google.golang.org/grpc@v1.83.2)
go_commands='go get go@1.26.0 toolchain@go1.26.10 "$@" && go mod tidy && go test -mod=readonly -race ./...'
container catalog "$go_image" bash -c "$go_commands" remediation "${common_go[@]}" "${catalog_go[@]}"
container orders "$go_image" bash -c "$go_commands" remediation "${common_go[@]}"
container checkout "$node_image" bash -c \
  'node .yarn/releases/yarn-4.11.0.cjs install && node .yarn/releases/yarn-4.11.0.cjs install --immutable && npm test'
severity=$(python3 -c 'import json,sys; print(",".join(json.load(open(sys.argv[1]))["security"]["blocked_severities"]))' "$stage/.ci/policy.json")
ignore_unfixed=$(python3 -c 'import json,sys; print(str(json.load(open(sys.argv[1]))["security"]["ignore_unfixed"]).lower())' "$stage/.ci/policy.json")
docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
  -v "$stage:/work" -w /work -e TRIVY_CACHE_DIR=/tmp/trivy aquasec/trivy:0.76.1 \
  fs --include-dev-deps --scanners vuln --severity "$severity" --ignore-unfixed="$ignore_unfixed" \
  --exit-code 1 --format json --output /work/reports/dependencies.json \
  --skip-dirs '**/node_modules,**/.yarn,**/dist,**/coverage' /work
python3 - "$root" "$stage" <<'PY'
import hashlib, json, pathlib, sys
root, stage = map(pathlib.Path, sys.argv[1:])
report = json.loads((stage / 'reports/dependencies.json').read_text())
required = {'src/admin/package-lock.json', 'src/ui/package-lock.json',
            'src/cart/requirements.txt', 'src/catalog/go.mod',
            'src/orders/go.mod', 'src/checkout/yarn.lock'}
results = report['Results']
missing = {name for name in required if not any(str(r.get('Target', '')).endswith(name) for r in results)}
policy = json.loads((stage / '.ci/policy.json').read_text())['security']
blocked = [v for r in results for v in r.get('Vulnerabilities', [])
           if v['Severity'] in policy['blocked_severities']]
if missing or blocked:
    raise SystemExit(f'Reporte de Trivy incompleto o bloqueado: faltantes={sorted(missing)}, hallazgos={len(blocked)}')
snapshot = json.loads((stage / 'snapshot.json').read_text())
changed = [name for name, sha in snapshot.items()
           if hashlib.sha256((root / name).read_bytes()).hexdigest() != sha]
if changed:
    raise SystemExit('Archivos locales modificados durante la ejecución; no se copió nada: ' + ', '.join(changed))
for name in snapshot:
    target = root / name
    temporary = target.with_name(target.name + '.remediation-tmp')
    temporary.write_bytes((stage / name).read_bytes())
    temporary.replace(target)
print('Dependencias y locks copiados después de aprobar pruebas y Trivy. Revisar git diff antes de commit/push.')
PY
