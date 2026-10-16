#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
# Pinned upstream manifests; keep an inspectable local copy.
if k -n argocd get deployment argocd-server >/dev/null 2>&1; then
  marker=$(k get namespace argocd -o jsonpath='{.metadata.labels.lab11-managed}')
  [[ $marker == true ]] || { echo 'Existing Argo installation: use its approved configuration; refusing overwrite'; exit 1; }
fi
k get namespace argocd >/dev/null 2>&1 || k create namespace argocd
k label namespace argocd lab11-managed=true --overwrite >/dev/null
curl -fsSL https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.2/manifests/install.yaml -o reports/lab11/argocd-install.yaml
k -n argocd apply --server-side -f reports/lab11/argocd-install.yaml
k -n argocd rollout status statefulset/argocd-application-controller --timeout=300s
for name in argocd-repo-server argocd-server; do k -n argocd rollout status deployment/"$name" --timeout=300s; done
k -n argocd patch configmap argocd-cm --type merge -p '{"data":{"application.resourceTrackingMethod":"annotation"}}'
