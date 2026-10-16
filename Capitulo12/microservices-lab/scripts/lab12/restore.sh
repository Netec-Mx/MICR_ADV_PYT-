#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
[[ "$(kubectl config current-context)" == "msvc-gateway" ]]
# Never discard an active experiment or remove finalizers.
[[ -z "$(kubectl -n chaos-testing get podchaos,networkchaos,stresschaos -l lab12-owned=true -o name)" ]] || { echo 'Hay fallos activos; esperar y recuperar antes de restaurar.'; exit 1; }
[[ -z "$(kubectl -n chaos-testing get configmap lab12-run-lock --ignore-not-found -o name)" ]]
helm rollback lab08-observability "$(cat reports/lab12/observability-revision.txt)" -n observability --wait --timeout 5m
rm reports/lab12/observability-revision.txt
# Retain Chaos Mesh installation and CRDs; other experiments may share them.
