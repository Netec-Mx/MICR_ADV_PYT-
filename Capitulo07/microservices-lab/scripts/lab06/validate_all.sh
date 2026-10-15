#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
KUBE_CONTEXT=${KUBE_CONTEXT:-msvc-gateway}
PYTHON_BIN=${PYTHON_BIN:-python}
k() { kubectl --context "$KUBE_CONTEXT" "$@"; }
for app in postgres keycloak-db redis zookeeper kafka; do k -n microservices rollout status "statefulset/$app" --timeout=120s; done
for app in keycloak order-service inventory-service users-service; do k -n microservices rollout status "deployment/$app" --timeout=120s; done
k -n traefik rollout status deployment/traefik --timeout=120s
"$PYTHON_BIN" scripts/lab06/validate_gateway.py
"$PYTHON_BIN" scripts/lab06/test_ratelimit.py
k apply -f k8s/traefik/chaos-route.yaml
"$PYTHON_BIN" scripts/lab06/test_circuitbreaker.py
printf '%s\n' 'Todas las comprobaciones del laboratorio 6 aprobaron.'
