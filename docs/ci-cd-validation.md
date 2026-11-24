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

## Revisión del fallo de Containers

En la ejecución [44846563637](https://github.com/PablodeMelo1/Tero/actions/runs/44846563637)
del commit `05bb3ad`, pasaron los tests de los seis servicios, SonarCloud,
Semgrep, Gitleaks, Trivy de dependencias y Checkov. Los seis builds Docker
también pasaron. Los seis jobs Containers fallaron después, al invocar el
escáner de imágenes: `FATAL unknown flag: --include-dev-deps`.

`scripts/trivy.sh` ahora agrega ese argumento únicamente en modo `fs`.
Las pruebas de regresión usan una CLI simulada que rechaza esa opción para
`image`, verifican que se mantiene en `fs` y que tanto los hallazgos como los
errores del escáner bloquean ambos modos. Se conservan HIGH/CRITICAL y el bloqueo
de vulnerabilidades sin arreglo. Falta validar el escaneo real de imágenes en
la siguiente ejecución; este fallo anterior ocurrió antes de analizar CVEs.

## Hallazgos reales de imágenes — 21/11/2026

La ejecución [44860905857](https://github.com/PablodeMelo1/Tero/actions/runs/44860905857)
del commit `e09e5f5` confirmó que SonarCloud, tests, Checkov y seguridad de código
pasan. Los seis builds también pasan. El gate de imágenes ahora completa el
escaneo y bloquea por vulnerabilidades; sus artifacts `scan-*` se descargaron
en `.cache/container-scans/44860905857/` para revisar los JSON completos.

| Imágenes | Hallazgos HIGH/CRITICAL |
|---|---|
| UI, Admin, Checkout, Catalog y Orders | 40 por imagen en paquetes Debian 12; 38 sin parche informado |
| Cart | 103 en Debian 12 (101 sin parche) y 3 en Starlette 0.38.6 |

Los tres hallazgos de Starlette son CVE-2024-47874, CVE-2026-48818 y
CVE-2026-54283; el mayor mínimo corregido informado es 1.3.1. Se preparó la
actualización compatible de FastAPI e Instrumentator y la migración de arranque
a lifespan.

El scanner de filesystem ahora incluye explícitamente `requirements.lock` y
`requirements-dev.lock` mediante `--file-patterns`: antes solo detectaba el
`requirements.txt` de dependencias directas. Las exclusiones de directorios de
fuente se limitan a `fs`, para que las imágenes también analicen los paquetes
instalados en `node_modules`. El JSON se convierte a tabla en el log sin un
segundo escaneo y se conserva el código de salida original. 47 pruebas locales
sin apertura de sockets aprobaron; incluyen evidencia visible, rechazo por
hallazgos y errores de ejecución/conversión. La política no se relajó.

La ejecución real de `.cache/update-cart-dependencies.sh` produjo
`.cache/cart-remediation.TWEGKQ/`: ambos locks locales coinciden con los generados
en esa copia, sus pruebas de Cart aprobaron antes de copiar y el reporte de
dependencias del 21/11/2026 a las 16:54 UTC tiene cero HIGH/CRITICAL. Las versiones
aplicadas son FastAPI 0.137.2, Starlette 1.3.1 e Instrumentator 8.1.0. La cobertura
total de Cart en ese reporte es 59.9 %; el umbral de SonarCloud se aplica al código
nuevo y debe confirmarse con el siguiente análisis.

Se revisaron los seis reportes reales de `.cache/base-image-scans/`, generados
entre 16:50 y 16:52 UTC, junto con sus digests de `imagetools inspect`:

| Base candidata | HIGH/CRITICAL | Decisión aplicada |
|---|---|---|
| Distroless static Debian 13 nonroot | 0 | Runtime de Catalog/Orders con compilación `CGO_ENABLED=0` |
| Node 22 Alpine 3.23 | 10, todos dentro de npm | Base de UI/Admin/Checkout; npm, Corepack y Yarn se eliminan físicamente de la etapa final |
| Python 3.12 Alpine 3.23 | 16 en krb5-libs 1.22.1-r0 | Base de Cart; se exige instalar krb5-libs >= 1.22.3-r0 |
| Node 22 slim trixie | 59 | No se seleccionó |
| Python 3.12 slim trixie | 51 | No se seleccionó |
| Distroless Node 22 Debian 13 nonroot | 1 sin parche en libssl3t64 | No se seleccionó |

Las nuevas bases externas están fijadas por los digests observados. Los servicios
Node conservan los gestores de paquetes en las etapas de build y sus dependencias
de producción en `/app/node_modules`. Go conserva su healthcheck ejecutable y
usuarios sin privilegios. El mantenimiento de Checkout usa `sh`, disponible en
Alpine, para regenerar locks. Se validaron las seis imágenes completas y la
integración real después de aplicar la corrección adicional de Go indicada abajo.

La primera comprobación de imágenes finales (`.cache/container-validation.Mq1twf/`)
aprobó UI, Admin y Checkout con cero HIGH/CRITICAL, incluidos sus paquetes Node
instalados. Catalog y Orders detectaron CVE-2026-97054 en la biblioteca estándar
Go 1.26.10. Se actualizó a 1.26.11 el builder fijado por digest, los dos `go.mod`,
el job Go de CI y la receta de mantenimiento. El digest del builder se verificó
en los [metadatos oficiales de Docker Library](https://github.com/docker-library/repo-info/blob/master/repos/golang/remote/1.26.11-bookworm.md).
Cart también aprobó su build sobre musl y el escaneo de su imagen final con cero
HIGH/CRITICAL. El reporte de dependencias y los 18 controles Checkov aprobaron.
La comprobación final `.cache/container-validation.OszCBO/` del 21/11/2026
reconstruyó los binarios con Go 1.26.11 y terminó aprobada:

| Verificación final | Resultado |
|---|---|
| Builds Docker | Los seis servicios compilan |
| Trivy de imágenes | Cero HIGH/CRITICAL en las seis imágenes finales |
| Trivy de dependencias | Cero HIGH/CRITICAL en los ocho manifiestos/locks detectados, incluidos ambos locks Python |
| Checkov | 18 controles aprobados, cero fallos |
| Integración con PostgreSQL/Redis | Stack healthy y smoke tests aprobados |
| Compra E2E | Catálogo → carrito → checkout → orden persistida aprobada |
| Integridad de la evidencia | Todos los hashes de entradas coinciden con los archivos actuales |

`success.json` y los siete reportes de Trivy de esa copia confirman el resultado.
Los temporales y reportes siguen excluidos de Git. Falta subir el commit y
confirmar el pipeline remoto sobre ese nuevo SHA; no se publicaron imágenes ni
se ejecutaron despliegues remotos durante esta validación local.
