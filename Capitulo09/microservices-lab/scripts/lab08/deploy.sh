#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
KUBE_CONTEXT=${KUBE_CONTEXT:-msvc-gateway}; PROFILE=${PROFILE:-msvc-gateway}
k() { kubectl --context "$KUBE_CONTEXT" "$@"; }
k -n vault rollout status statefulset/vault --timeout=120s
# Recover Vault dev if it restarted; existing secrets retain rotated values.
bash scripts/lab07/bootstrap.sh
for app in order-service inventory-service users-service; do k -n microservices rollout status "deployment/$app" --timeout=300s; done
for namespace in observability monitoring; do k create namespace "$namespace" --dry-run=client -o yaml | k apply -f -; done
helm lint observability/chart
helm upgrade --install lab08-observability observability/chart --namespace observability --kube-context "$KUBE_CONTEXT" --wait --timeout=300s
for service in order-service inventory-service users-service; do
 minikube -p "$PROFILE" image build -t "$service:lab08" -f "$service/Dockerfile" .
done
k apply -f k8s/lab08/50-apps.yaml
for service in inventory-service order-service users-service; do k -n microservices rollout status "deployment/$service" --timeout=300s; done
printf '%s\n' 'Lab08 listo. Conserva Keycloak/Traefik y abre los port-forward descritos en LAB08.md.'
