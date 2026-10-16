#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
KUBE_CONTEXT=${KUBE_CONTEXT:-msvc-gateway}; PROFILE=${PROFILE:-msvc-gateway}; PYTHON_BIN=${PYTHON_BIN:-python3}
[[ "$KUBE_CONTEXT" == msvc-gateway && "$PROFILE" == msvc-gateway ]]
k() { kubectl --context "$KUBE_CONTEXT" "$@"; }
h() { helm --kube-context "$KUBE_CONTEXT" "$@"; }
i() { istioctl --context "$KUBE_CONTEXT" "$@"; }
mkdir -p reports/lab10
SERVICES=(order-service inventory-service users-service)
