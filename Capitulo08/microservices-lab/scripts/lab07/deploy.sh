#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
KUBE_CONTEXT=${KUBE_CONTEXT:-msvc-gateway}; PROFILE=${PROFILE:-msvc-gateway}
k() { kubectl --context "$KUBE_CONTEXT" "$@"; }
k -n microservices rollout status deployment/keycloak --timeout=180s
k create namespace vault --dry-run=client -o yaml | k apply -f -
helm upgrade --install vault vendor/vault-0.34.1.tgz --namespace vault --kube-context "$KUBE_CONTEXT" --values k8s/lab07/vault-values.yaml --wait --timeout=300s
k -n vault rollout status statefulset/vault --timeout=300s
bash scripts/lab07/bootstrap.sh
k apply -f k8s/lab07/01-identities.yaml
for service in order-service inventory-service users-service; do
  minikube -p "$PROFILE" image build -t "$service:lab07" -f "$service/Dockerfile" .
done
k apply -f k8s/lab07/50-apps.yaml
for service in order-service inventory-service users-service; do
  k -n microservices rollout status "deployment/$service" --timeout=300s
done
# Only after all new pods are Ready, remove the legacy application secret keys.
k apply -f k8s/lab07/02-platform-secrets.yaml
printf '%s\n' 'Lab07 desplegado; conserva los port-forward de Keycloak y Traefik del Lab06.'
