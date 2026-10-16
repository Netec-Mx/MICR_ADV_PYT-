# Verificación del laboratorio 11

Fecha de revisión: 2026-10-08. Solución acumulativa sobre el Lab 10.

## Resultados ejecutados

**182 pruebas locales aprobadas; 74 omitidas por infraestructura no disponible.** No se cuentan de nuevo las repeticiones de las mismas suites.

| Suite | Aprobadas | Omitidas |
|---|---:|---:|
| Orders, incluidos los dos tests del endpoint de release | 59 | 62 |
| Inventory y contratos migrados a Schemathesis 4 | 46 | 11 |
| Users | 6 | 1 |
| Empaquetado, mesh y nuevos contratos GitOps | 71 | 0 |
| Total | 182 | 74 |

Las omisiones necesitan PostgreSQL, Redis o Keycloak reales. El entorno no tiene Docker ni un clúster disponible. La cobertura local de Orders, con esas omisiones, es **63%**: **no acredita el gate ≥80%**. El pipeline inicia dependencias CI aisladas, exige variables de integración, aplica `--cov=app --cov-fail-under=80` y rechaza JUnit con pruebas omitidas. No se redujo el umbral, no se excluyeron módulos de Orders y no se reportó una aprobación de CI que no ocurrió.

Los nuevos tests ejercitan promoción y reversión con repositorios Git locales reales, rechazo de cambios concurrentes, limpieza de worktree, metadata por digest/SHA, estado Synced/Healthy en la revisión exacta y recuperación tanto por readiness fallida como por smoke fallido. La prueba de preparación usa respuestas Helm capturadas de fixture y render Helm real; no simula que un clúster se adoptó correctamente.

## Dependencias y archivos

- Instalación conjunta de las dependencias de desarrollo revisadas de los tres servicios en Python 3.12: resuelta. `pip check`: sin conflictos.
- Se reemplazó Schemathesis 3.34.0 incompatible con las dependencias actualizadas por 4.30.0 y se migraron las llamadas de contrato de Orders e Inventory. Pytest 8.4.2 y pytest-asyncio 0.26.0.
- La generación positiva usa representación JSON entera canónica en cantidades/stock; las pruebas negativas explícitas de tipos estrictos se conservan. No se desactivaron los checks de respuesta.
- Se validaron **26 instancias de recursos renderizados** contra el esquema oficial Kubernetes 1.35.8: tres servicios en modo base y en modo mesh. Son estados alternativos con nombres compartidos, no 26 recursos distintos de un despliegue.
- Se verificó que Orders v1 puede usar GHCR y v2 conservar el registry original, con dos réplicas, UID 10001, identidad Vault original y referencia al Secret de pull.
- Sintaxis de los archivos Python y de todos los scripts Bash nuevos: válida.
- Workflow parseado y comprobado: jobs dependientes, artifact de la misma imagen, scan antes de push, publicación fuera de PR y acciones fijadas por SHA.
- Application y AppProject preparados: válidos contra los schemas CRD oficiales de Argo CD 3.5.2.
- Se obtuvo el manifiesto upstream Argo CD 3.5.2; sus imágenes referencian esa versión. No se instaló en Kubernetes.

## Límites de esta revisión

No se ejecutaron Docker build/push, Trivy sobre la imagen resultante, GitHub Actions ni Argo CD en un clúster. No se acreditaron cobertura completa, cero CRITICAL, image pull, auto-sync, self-healing, rolling update ni recuperación real de pods. Tampoco se enviaron commits a repositorios del usuario.

La guía incluye pruebas para esos resultados y exige evidencia del SHA, digest, estado Argo y HTTP autenticado. El observador debe permanecer activo; Kubernetes no realiza rollback automático de un Deployment por probes y Argo no revierte automáticamente un commit defectuoso.

La limpieza elimina la Application sin finalizer/cascada y recupera valores capturados con un chart compatible. Conserva imágenes, datos, backends, el mesh, Argo instalado y repositorios.
