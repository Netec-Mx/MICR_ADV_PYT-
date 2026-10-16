#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
KUBE_CONTEXT=${KUBE_CONTEXT:-msvc-gateway}
PYTHON_BIN=${PYTHON_BIN:-python}
k() { kubectl --context "$KUBE_CONTEXT" "$@"; }
k -n vault rollout status statefulset/vault --timeout=120s
for app in order-service inventory-service users-service; do
 k -n microservices rollout status "deployment/$app" --timeout=120s
 if [[ "$(k auth can-i create tokenreviews.authentication.k8s.io --as="system:serviceaccount:microservices:$app")" != no ]]; then
  printf '%s\n' 'Application ServiceAccount must not have TokenReview permission.' >&2; exit 1
 fi
done
[[ "$(k auth can-i create tokenreviews.authentication.k8s.io --as=system:serviceaccount:vault:vault)" == yes ]]
bash scripts/lab07/check_acl.sh
"$PYTHON_BIN" scripts/lab07/validate_vault.py
# Preserve actual Lab06 behavior: products, Orders, Kafka reservation and gateway routes.
"$PYTHON_BIN" scripts/lab06/validate_gateway.py
k -n vault exec vault-0 -- cat /vault/audit/audit.json | "$PYTHON_BIN" scripts/lab07/audit_report.py
printf '%s\n' 'Lab07: identidad, ACL, rotación, renovación, continuidad y auditoría aprobadas.'
