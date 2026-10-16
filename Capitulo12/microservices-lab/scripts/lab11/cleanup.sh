#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
test -s reports/lab11/before-values.yaml
# No finalizer is used: deleting this Application orphans workloads intentionally.
k -n argocd delete application lab11-orders --ignore-not-found
k -n argocd delete appproject lab11 --ignore-not-found
helm --kube-context "$KUBE_CONTEXT" upgrade order-service helm/msvc-chart -n microservices -f reports/lab11/before-values.yaml --atomic --wait --timeout 300s
# Secret is no longer referenced after Helm recovery.
k -n microservices delete secret lab11-ghcr-pull --ignore-not-found
printf '%s\n' 'Orders returned to Helm management. Argo, Git repos, images, data, backends and Istio remain available.'
