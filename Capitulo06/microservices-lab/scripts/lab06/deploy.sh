#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
KUBE_CONTEXT=${KUBE_CONTEXT:-msvc-gateway}
PROFILE=${PROFILE:-msvc-gateway}
PYTHON_BIN=${PYTHON_BIN:-python}
k() { kubectl --context "$KUBE_CONTEXT" "$@"; }
k cluster-info >/dev/null
"$PYTHON_BIN" scripts/keycloak/setup_realm.py
"$PYTHON_BIN" scripts/lab06/render_config.py
for service in order-service inventory-service users-service; do
  minikube -p "$PROFILE" image build -t "$service:lab06" -f "$service/Dockerfile" .
done
for path in 00-namespace 01-secrets 02-postgres-init 03-keycloak-realm 10-databases; do
  k apply -f "k8s/lab06/$path.yaml"
done
for app in postgres keycloak-db; do k -n microservices rollout status "statefulset/$app" --timeout=300s; done
k apply -f k8s/lab06/20-messaging.yaml
for app in redis zookeeper kafka; do k -n microservices rollout status "statefulset/$app" --timeout=300s; done
for topic in orders.created inventory.stock-reserved inventory.stock-failed order-events; do
  k -n microservices exec statefulset/kafka -- kafka-topics --bootstrap-server kafka:9092 --create --if-not-exists --topic "$topic" --partitions 3 --replication-factor 1
done
k apply -f k8s/lab06/30-keycloak.yaml
k -n microservices rollout status deployment/keycloak --timeout=300s
# A completed Job is immutable; only this idempotent migration Job is recreated.
k -n microservices delete job eventstore-migrate --ignore-not-found=true --wait=true
k apply -f k8s/lab06/40-migration.yaml
k -n microservices wait --for=condition=complete job/eventstore-migrate --timeout=180s
k apply -f k8s/lab06/50-apps.yaml
for app in inventory-service order-service users-service; do k -n microservices rollout status "deployment/$app" --timeout=300s; done
helm show crds vendor/traefik-41.7.0.tgz | k apply --server-side --field-manager=lab06-crds -f -
helm upgrade --install traefik vendor/traefik-41.7.0.tgz --namespace traefik --kube-context "$KUBE_CONTEXT" --values k8s/traefik/values.yaml --wait --timeout=300s
k wait --for=condition=Established crd/ingressroutes.traefik.io crd/middlewares.traefik.io --timeout=120s
k apply -f k8s/traefik/middlewares.yaml
k apply -f k8s/traefik/routes.yaml
printf '%s\n' 'Despliegue listo. Abre port-forward de Keycloak y Traefik según LAB06.md.'
