# Verificación de la revisión · Lab 9

Fecha: 2026-10-08. Alcance: materiales acumulativos y dependencias corregidas. Las cifras siguientes corresponden a operaciones realmente ejecutadas.

| Verificación | Resultado |
|---|---|
| Regresión Orders con dependencias corregidas | 119 pruebas aprobadas |
| Regresión Inventory con dependencias corregidas | 57 pruebas aprobadas |
| Regresión Users con dependencias corregidas | 7 pruebas aprobadas |
| Vault e integración SDK OTLP | 29 pruebas aprobadas |
| Observabilidad, incluyendo versiones 9.0.0/9.1.0 en recursos OTEL | 8 pruebas aprobadas |
| Empaquetado: informes, chart, valores inválidos y verificación de release | 30 pruebas aprobadas |
| **Total de pruebas distintas** | **250 aprobadas; 1 prueba del stack completo omitida** |
| Helm 3.20.1: template/lint | Tres servicios renderizados y chart validado |
| Esquema Kubernetes 1.35.8 | 12 recursos del chart válidos; identidades y selectores del Lab 8 preservados |
| Sintaxis | Python y scripts Bash del Lab 9 comprobados |
| Resolución/instalación de dependencias | Locks Python 3.12/Linux resueltos con wheels; conjunto corregido instalado para la regresión |
| Trivy | Binario 0.75.0 descargado con SHA-256 comprobado; análisis real de seis locks Python |

No se sumaron dos veces las ocho pruebas de observabilidad, que se ejecutaron tanto con la suite acumulativa como con la de empaquetado. Se usaron PostgreSQL, Redis y Keycloak reales para la regresión; Vault real con un doble de TokenReview para la integración de identidad. Las pruebas OTLP usaron un receptor gRPC de prueba y backends Prometheus/Alertmanager reales. No se ejecutó un broker Kafka ni un clúster Kubernetes en este entorno.

La prueba opcional con el stack completo Collector/Jaeger/Grafana/Prometheus/Alertmanager se omitió por restricciones del entorno para métricas de proceso/procfs e IPC Unix. Esa omisión no constituye validación del despliegue completo.

## Dependencias: hallazgos observados

| Servicio | Hallazgos antes | HIGH/CRITICAL antes | Hallazgos después | HIGH/CRITICAL después |
|---|---:|---:|---:|---:|
| order-service | 7 | 3 | 0 | 0 |
| inventory-service | 7 | 3 | 0 | 0 |
| users-service | 7 | 3 | 0 | 0 |

Los hallazgos heredados correspondían a Starlette 0.37.2. La remediación combina FastAPI 0.143.0, Starlette 1.7.0, Pydantic 2.14.0 y Prometheus FastAPI Instrumentator 8.1.0. Se fijaron los transitivos en los locks y se ejecutó toda la regresión indicada arriba.

Los JSON originales del escaneo y la fecha de la base están en `dependency-review/`. **Estos resultados cubren dependencias Python, no imágenes ni paquetes del sistema operativo.** No equivalen a una certificación de seguridad ni a afirmar ausencia de vulnerabilidades desconocidas.

## Operaciones pendientes en el clúster del alumno

El entorno de revisión no tiene Docker/minikube. No se construyeron imágenes; no se midió aquí la reducción ≥40%; no se escanearon imágenes completas; no se publicaron imágenes ni se ejecutó adopción, rollout o rollback en Kubernetes.

Los scripts incluidos implementan esas comprobaciones, usando tamaños e informes reales, preflight del API server, descargas por digest, recursos Ready y lectura de versión/UID dentro de los pods. Sus pruebas locales incluyen casos negativos para evitar aprobar informes faltantes, pods no Ready, digests incorrectos, ejecución root, versión incorrecta o release fallido. Estos casos verifican los comprobadores, no sustituyen el ejercicio real en minikube.
