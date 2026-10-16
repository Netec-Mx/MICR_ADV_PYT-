#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
[[ "$(kubectl config current-context)" == "msvc-gateway" ]] || { echo 'Se requiere el contexto local msvc-gateway'; exit 1; }
mkdir -p reports/lab12
[[ ! -f reports/lab12/observability-revision.txt ]] || { echo 'Preparación previa presente; restaura antes de repetir.'; exit 1; }
helm history lab08-observability -n observability -o json | python -c 'import json,sys; print(json.load(sys.stdin)[-1]["revision"])' > reports/lab12/observability-revision.txt
helm upgrade lab08-observability observability/chart -n observability --reuse-values --set lab12.enabled=true --wait --timeout 5m
kubectl create namespace chaos-testing --dry-run=client -o yaml | kubectl apply -f -
RUNTIME=$(kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.containerRuntimeVersion}')
case "$RUNTIME" in
 containerd://*) CRI=containerd; SOCKET=/run/containerd/containerd.sock ;;
 docker://*) CRI=docker; SOCKET=/var/run/docker.sock ;;
 *) echo "Runtime no soportado automáticamente: $RUNTIME"; exit 1 ;;
esac
minikube -p msvc-gateway ssh -- "sudo test -S $SOCKET"
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm repo update chaos-mesh
helm upgrade --install lab12-chaos chaos-mesh/chaos-mesh --version 2.8.4 -n chaos-testing --set controllerManager.replicaCount=1 --set dashboard.create=false --set chaosDaemon.runtime="$CRI" --set chaosDaemon.socketPath="$SOCKET" --wait --timeout 5m
kubectl -n monitoring rollout status deploy/prometheus --timeout=180s
