#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$ROOT"
PYTHON_BIN=${PYTHON_BIN:-python3}
export KUBE_CONTEXT=${KUBE_CONTEXT:-msvc-gateway}
mkdir -p reports/lab11
k() { kubectl --context "$KUBE_CONTEXT" "$@"; }
