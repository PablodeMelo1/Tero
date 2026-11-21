# Validación local de la implementación

Pruebas ejecutadas el 28 de octubre de 2026. No se publicaron imágenes ni se
desplegó en servidores externos; no hay credenciales de esos servicios configuradas
por esta implementación.

| Verificación | Resultado |
|---|---|
| YAML de los tres workflows | `actionlint` sin errores |
| Scripts | Validación de sintaxis Bash y compilación Python |
| Build | Las seis imágenes compilan |
| UI | Pruebas HTTP de página, health y cuatro proxies aprobadas |
| Admin | Pruebas de autenticación, cookie, logout y rechazo de acceso aprobadas |
| Checkout | Cálculos, shipping, persistencia, submit y error de Orders aprobados |
| Cart | Ciclo HTTP de carrito y merge de sesiones aprobados |
| Go | Pruebas con `-race`, seed del catálogo, DSN, JSON inválido y sondas de salud aprobadas |
| Gates | Bloquean métricas faltantes, baja cobertura, bugs, CVEs, SHA incorrecto y tags mutables |
| Despliegue | Éxito y rollback probados con servidor HTTP y Docker simulado |
| Integración real | Stack de ocho contenedores healthy y smoke tests aprobados |
| Compra real | Catálogo → carrito → checkout → orden persistida en PostgreSQL |
| Semgrep | 6 reglas sobre 49 archivos, sin hallazgos |
| Gitleaks | Sin hallazgos en historial ni archivos analizados |
| Checkov | 18 controles seleccionados aprobados sobre los seis Dockerfiles |
| ZAP baseline | UI y admin sin alertas High; otros hallazgos quedan en sus reportes |
| Trivy | Gate bloqueado por CVEs HIGH/CRITICAL en dependencias e imágenes |

Los reportes locales se guardan en `reports/`, excluido de Git: `dependencies.json`,
`image-*.json`, `checkov-docker.json`, `semgrep.json`, `gitleaks-*.json`, `zap-*.json`,
`zap-*.html`, `smoke.log`, `e2e.log` e `integration.log`. La cobertura queda bajo
`src/<servicio>/coverage/` o `coverage.out`.

Los CVEs incluyen dependencias de Go y checkout y paquetes de las bases Debian y
los runtimes. La política incluye vulnerabilidades sin arreglo disponible; no se
agregaron ignores para hacer pasar el pipeline. Actualizar dependencias e imágenes
y repetir los escaneos antes de intentar publicar una release.

Queda por verificar contra servicios reales: análisis y métricas de SonarCloud,
publicación en Docker Hub, reglas de los GitHub Environments, SSH y despliegues
remotos. Los archivos y comandos de configuración están en [ci-cd.md](ci-cd.md).

## Revisión del hallazgo de SonarCloud sobre el reporte de métricas — 20/11/2026

Hallazgo: `Path Traversal via file content in sonar_gate.main()`. Se propone
clasificarlo como **False positive**: la respuesta HTTP es contenido JSON y
no interviene en la ruta literal `reports/sonar-measures.json`
([CWE-22](https://cwe.mitre.org/data/definitions/22.html)). No se suprimió la regla.
`tests/test_sonar_gate.py` comprueba que nombres con `../` y rutas absolutas
recibidos desde la API se conservan como contenido y no alteran el destino.
La prueba y las cuatro verificaciones existentes de políticas aprobaron.

## Correcciones de SonarCloud y cobertura — 20/11/2026

| Hallazgo recibido | Cambio |
|---|---|
| Inyección de argumentos en `github_environments.api()` | Lista permitida de rutas y métodos, validación del repositorio y reviewer, host `github.com` fijo, separador `--` y `shell=False`; JSON por stdin |
| Path Traversal en `manifest.py` | Se eliminó el argumento de ruta: lectura literal de `manifest.json` y validación del SHA y de los seis digests |
| Path Traversal en `zap_gate.py` | Reporte JSON por stdin; el gate conserva el rechazo de alertas High y evidencia faltante |
| Ejecución de setup scripts por pip | `--only-binary=:all:` junto con `--require-hashes`, tanto en CI como en la imagen Cart |
| Cobertura de los scripts ausente | Reporte propio `coverage-ci`, importación en SonarCloud y pruebas de contratos, fallos y entradas maliciosas |
| Clasificación y duplicación de tests | Se retiraron las propiedades de alcance que el scanner indicó que ignora; exclusión de tests solo para métricas, manteniendo su análisis |

Validación de esta revisión: 38 pruebas Python locales aprobadas; cobertura de
líneas y ramas de los scripts Python de 95 % (Coverage.py 7.17.0, motor Python).
Este porcentaje corresponde a `scripts/*.py`, no al código nuevo del PR completo.
La prueba de despliegue con servidor HTTP y las pruebas HTTP de UI/Admin no se
pudieron verificar en esta sesión: el entorno rechaza la apertura de sockets
con `EPERM`. Siguen incluidas en CI. Docker y los escáneres en contenedor tampoco
están disponibles en esta sesión. El nuevo análisis remoto y los builds con
instalación exclusiva de wheels quedan pendientes de la siguiente ejecución.

El reporte de Trivy de `.cache/dependency-remediation.AWu3EI/reports/dependencies.json`
del 20/11/2026 dejó tres hallazgos HIGH/CRITICAL: CVE-2026-78661 en `x/net`
de Catalog y Orders, y CVE-2026-4926 en `path-to-regexp` de Checkout. El script
se detuvo antes de copiar los locks. Se ajustó `remediate-dependencies.sh` para
`x/net v0.62.0` con sus versiones requeridas de crypto/text y para forzar
`path-to-regexp 8.4.2`. Sus fuentes oficiales son
[go.mod de x/net](https://github.com/golang/net/blob/v0.62.0/go.mod) y
[package.json de path-to-regexp](https://github.com/pillarjs/path-to-regexp/blob/v8.4.2/package.json).
La siguiente ejecución real del usuario produjo
`.cache/dependency-remediation.mxVRkj/reports/dependencies.json`, con fecha
`2026-11-21T00:09:47Z` (20/11 en Montevideo). Trivy 0.76.1 analizó los seis
servicios y no encontró HIGH/CRITICAL. Se verificó que los seis archivos locales
de dependencias coinciden exactamente con los generados en esa copia de trabajo.
El script exige pruebas Go con `-race`, instalación Yarn immutable y pruebas de
Checkout antes de escanear y copiar los archivos. Esta ejecución deja aplicada
la remediación local; el resultado no cubre las imágenes ni sustituye el nuevo
pipeline en GitHub. Las pruebas con Docker simulado solo validan la copia y el
bloqueo.

No se suprimieron reglas ni se bajaron umbrales. Los hallazgos enviados necesitan
un nuevo análisis para comprobar su cierre; el falso positivo del reporte de
SonarCloud requiere clasificación en ese servicio con la evidencia anterior.

## Revisión del hallazgo en normalize_coverage.normalize()

Hallazgo: `Path Traversal via file content in normalize_coverage.normalize()`.
La clasificación recomendada es **False positive**. `report` se construye con
`src`, un servicio de la lista permitida y el sufijo literal `coverage/lcov.info`;
ningún dato leído del reporte interviene en ese destino. El argumento de
`write_text()` es el contenido que se escribe. Además, `source_path()` rechaza
componentes `..` y rutas absolutas fuera del repositorio en los campos `SF:`.

Dos pruebas de regresión de `CoveragePathTests` verifican los tres servicios
TypeScript: las rutas en metadatos LCOV permanecen como contenido, solo cambia
el reporte previsto y los campos `SF:` inválidos abortan sin sobrescribir el
reporte ni otro archivo. La suite local sin apertura de sockets pasa 40 pruebas.
No se cambió el comportamiento del normalizador ni se suprimió la regla.
La clasificación del issue debe realizarse en SonarCloud; estas pruebas no
modifican su estado remoto.
