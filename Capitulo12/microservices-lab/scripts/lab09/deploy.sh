#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
k -n vault rollout status statefulset/vault --timeout=120s
bash scripts/lab07/bootstrap.sh
# Preflight all charts before any adoption. Capture existing manifests for recovery.
for svc in "${SERVICES[@]}"; do
 h lint helm/msvc-chart -n microservices -f "helm/values/$svc.yaml" -f "$REPORTS/$svc-image.yaml"
 h template "$svc" helm/msvc-chart -n microservices -f "helm/values/$svc.yaml" -f "$REPORTS/$svc-image.yaml" > "$REPORTS/$svc-rendered.yaml"
 k apply --dry-run=server -f "$REPORTS/$svc-rendered.yaml" >/dev/null
 for resource in "deployment/$svc" "service/$svc" "serviceaccount/$svc"; do
  checkpoint="$REPORTS/${resource//\//-}-before.json"
  # Keep the first captured state if this deploy is retried after a partial failure.
  if [[ ! -f "$checkpoint" ]]; then k -n microservices get "$resource" -o json > "$checkpoint"; fi
  owner=$(k -n microservices get "$resource" -o 'jsonpath={.metadata.annotations.meta\.helm\.sh/release-name}')
  owner_ns=$(k -n microservices get "$resource" -o 'jsonpath={.metadata.annotations.meta\.helm\.sh/release-namespace}')
  [[ -z "$owner_ns" || "$owner_ns" == microservices ]] || { echo "Owned in another namespace: $resource"; exit 1; }
  [[ -z "$owner" || "$owner" == "$svc" ]] || { echo "Owned by another release: $resource"; exit 1; }
 done
done
for svc in "${SERVICES[@]}"; do
 for resource in "deployment/$svc" "service/$svc" "serviceaccount/$svc"; do
  k -n microservices label "$resource" app.kubernetes.io/managed-by=Helm --overwrite
  k -n microservices annotate "$resource" "meta.helm.sh/release-name=$svc" meta.helm.sh/release-namespace=microservices --overwrite
 done
 # First install deliberately has no --atomic: failed install must not delete adopted Lab 8 objects.
 h upgrade --install "$svc" helm/msvc-chart -n microservices -f "helm/values/$svc.yaml" -f "$REPORTS/$svc-image.yaml" --wait --timeout=300s
 k -n microservices rollout status "deployment/$svc" --timeout=300s
done
h list -n microservices
"$PYTHON_BIN" scripts/lab09/verify_release.py --version "$VERSION"
