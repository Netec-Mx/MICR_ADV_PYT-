#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
PROFILE=${PROFILE:-msvc-gateway}; KUBE_CONTEXT=${KUBE_CONTEXT:-msvc-gateway}
PYTHON_BIN=${PYTHON_BIN:-python3}; VERSION=${VERSION:-9.0.0}
[[ "$PROFILE" == msvc-gateway && "$KUBE_CONTEXT" == msvc-gateway ]] || { echo 'Use cumulative profile/context msvc-gateway'; exit 1; }
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'Invalid VERSION'; exit 1; }
k() { kubectl --context "$KUBE_CONTEXT" "$@"; }
h() { helm --kube-context "$KUBE_CONTEXT" "$@"; }
SERVICES=(order-service inventory-service users-service)
REPORTS="reports/lab09/$VERSION"; mkdir -p "$REPORTS"
