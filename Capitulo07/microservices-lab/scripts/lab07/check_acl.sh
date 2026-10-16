#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
KUBE_CONTEXT=${KUBE_CONTEXT:-msvc-gateway}
for service in order-service inventory-service users-service; do
 kubectl --context "$KUBE_CONTEXT" -n microservices exec -i "deployment/$service" -- python - < scripts/lab07/acl_probe.py
done
