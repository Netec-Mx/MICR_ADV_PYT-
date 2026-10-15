#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
KUBE_CONTEXT=${KUBE_CONTEXT:-msvc-gateway}; PYTHON_BIN=${PYTHON_BIN:-python}
k() { kubectl --context "$KUBE_CONTEXT" "$@"; }
for app in otel-collector jaeger; do k -n observability rollout status "deployment/$app" --timeout=120s; done
for app in prometheus alertmanager grafana; do k -n monitoring rollout status "deployment/$app" --timeout=120s; done
for app in order-service inventory-service users-service; do k -n microservices rollout status "deployment/$app" --timeout=120s; done
bash scripts/lab07/check_acl.sh
"$PYTHON_BIN" scripts/lab08/test_trace.py
"$PYTHON_BIN" scripts/lab08/validate_logs.py
"$PYTHON_BIN" scripts/lab08/generate_traffic.py --seconds 30
"$PYTHON_BIN" scripts/lab08/validate_backends.py
"$PYTHON_BIN" scripts/lab08/test_alert.py
"$PYTHON_BIN" scripts/lab06/validate_gateway.py
printf '%s\n' 'Lab08: Vault, traza exacta, RED, Grafana, alerta y negocio acumulativo aprobados.'
