# Verificación · Revisión del Lab 12

Fecha: 2026-10-08. Evidencia técnica local; no es un postmortem de producción.

| Comprobación | Resultado |
|---|---|
| pytest de Lab12 | 11 passed |
| k6 2.0.0 contra fixture HTTP | PASS: OAuth, Host/JWT, lecturas, creación de pedidos, thresholds y muestras JSON |
| Remote write a Prometheus 3.15.0 real | PASS: counters, Rates y Trends recibidos |
| Latencia exportada | `k6_lab12_latency_p95`, segundos; resumen local en milisegundos |
| Reglas combinadas | 10 reglas válidas con promtool |
| Tests de recording rules | PASS: disponibilidad 0.5, burn 100, fracción rápida 0.8; sin tráfico devuelve serie vacía |
| Cuatro CRs de caos | PASS contra OpenAPI oficial Chaos Mesh 2.8.4 |
| Helm lint activado/desactivado | PASS |
| Chart activado | 24 recursos válidos contra OpenAPI Kubernetes 1.35.8, normalizando IntOrString |
| Chart desactivado vs Lab11 | Semánticamente equivalente, salvo checksum de configuración recalculado |
| Bash/Python | Sintaxis/compilación correctas |

pytest cubre presupuesto, ausencia de datos, transporte fallido como latencia fallida, límites de fases, conformidad/rechazo de contratos, clasificación de HTTP real y bloqueos ante contexto incorrecto/experimento activo. Schemathesis FailureGroup se captura explícitamente; los mensajes guardados redactan el token.

El fixture prueba al generador y su salida; no implementa el negocio, Istio, PostgreSQL, Kafka, Redis, Vault o Argo. Sus resultados no representan la disponibilidad/latencia del curso.

## Reproducir

En el entorno Python 3.12 del curso:

```bash
python -m pytest -q tests/lab12/test_review.py
cd tests/lab12
promtool test rules prometheus-test.yaml
```

Desde la raíz, con las CRDs extraídas del chart oficial y los binarios:

```bash
export CHAOS_CRDS=/ruta/chaos-mesh/crds
export K6=/ruta/k6
export HELM=/ruta/helm
export PROMTOOL=/ruta/promtool
export PROMETHEUS=/ruta/prometheus
python tests/lab12/verify.py
```

El verificador usa puerto local 19090 para Prometheus; debe estar libre. Inicia/detiene sus propios procesos HTTP/Prometheus, escribe resultados temporales y no accede al clúster.

## Pendiente en minikube

Instalación efectiva del daemon/webhooks; inyección AllInjected; restauración de red/CPU; reemplazo de pods; tráfico JWT/mTLS real; reservas de pedidos; presentación de Grafana y entrega de alertas; recuperación Ready/Argo Synced/Healthy. El SLO mensual no se puede demostrar con retención de 2 días.

No se ejecutaron/publicaron pipelines, no se modificaron repositorios externos y no se atribuyen los tests históricos de Labs 1–11 a esta revisión.
