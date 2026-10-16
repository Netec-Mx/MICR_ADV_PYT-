#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
k -n vault rollout status statefulset/vault --timeout=120s
bash scripts/lab07/bootstrap.sh
"$PYTHON_BIN" scripts/lab10/render-values.py
# Preflight all releases. Stage 100/0 leaves v2 ready but with no canary traffic.
for svc in "${SERVICES[@]}"; do
 h template "$svc" helm/msvc-chart -n microservices -f "helm/values/$svc.yaml" -f "helm/values/lab10-$svc.yaml" -f "reports/lab10/$svc-images.yaml" > "reports/lab10/$svc-rendered.yaml"
 k apply --dry-run=server -f "reports/lab10/$svc-rendered.yaml" >/dev/null
done
k apply -f istio/gateway.yaml
k apply -f istio/destination-rules.yaml
k apply -f istio/routes-100-0.yaml
# Controlled ingress transition; baseline applications initially remain permissive.
for svc in inventory-service order-service users-service; do
 h upgrade "$svc" helm/msvc-chart -n microservices -f "helm/values/$svc.yaml" -f "helm/values/lab10-$svc.yaml" -f "reports/lab10/$svc-images.yaml" --atomic --wait --timeout=300s
done
"$PYTHON_BIN" scripts/lab10/check-sidecars.py
# STRICT is applied only after all application sidecars are ready.
k apply -f istio/security.yaml
h upgrade lab08-observability observability/chart -n observability --reuse-values --set mesh.enabled=true --wait --timeout=300s
i analyze -n microservices --failure-threshold Error
printf '%s\n' 'Open gateway/Keycloak/observability port-forwards. Run mTLS, business, canary and metrics checks.'
