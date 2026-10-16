#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
# Explicitly restore the recorded Lab 9 revisions; never delete data/PVC/namespace/Istio CRDs.
k delete -f istio/security.yaml --ignore-not-found=true
k delete -f istio/routes-100-0.yaml --ignore-not-found=true
k delete -f istio/destination-rules.yaml --ignore-not-found=true
k delete -f istio/gateway.yaml --ignore-not-found=true
for svc in inventory-service order-service users-service; do
 rev=$("$PYTHON_BIN" -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "reports/lab10/$svc-before.json")
 h rollback "$svc" "$rev" -n microservices --wait --timeout=300s
 h get values "$svc" -n microservices --all -o json > "reports/lab10/$svc-values-restored.json"
 # Lab10 added a new chart value; compare only keys present in the original chart values.
 "$PYTHON_BIN" -c 'import json,sys; old=json.load(open(sys.argv[1])); now=json.load(open(sys.argv[2])); assert all(now[k]==v for k,v in old.items())' "reports/lab10/$svc-values-before.json" "reports/lab10/$svc-values-restored.json"
done
rev=$("$PYTHON_BIN" -c 'import json; print(json.load(open("reports/lab10/observability-before.json"))["version"])')
h rollback lab08-observability "$rev" -n observability --wait --timeout=300s
printf '%s\n' 'Lab9 revisions restored. Point your gateway port-forward back to Traefik. Istio installation retained.'
