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
