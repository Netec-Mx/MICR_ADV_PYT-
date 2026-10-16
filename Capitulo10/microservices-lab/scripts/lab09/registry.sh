#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
command -v skopeo >/dev/null
minikube -p "$PROFILE" addons enable registry
k -n kube-system rollout status deployment/registry --timeout=180s
k -n kube-system rollout status daemonset/registry-proxy --timeout=180s
k -n kube-system port-forward service/registry 15000:80 > "$REPORTS/registry-forward.log" 2>&1 &
LAB09_FORWARD_PID=$!
trap 'kill "$LAB09_FORWARD_PID" 2>/dev/null || true' EXIT
for attempt in {1..30}; do curl -fsS http://127.0.0.1:15000/v2/ >/dev/null && break; sleep 1; done
curl -fsS http://127.0.0.1:15000/v2/ >/dev/null
for svc in "${SERVICES[@]}"; do
 # Skopeo's HTTP client runs on the host: no Docker-daemon localhost confusion.
 if skopeo inspect --tls-verify=false "docker://127.0.0.1:15000/$svc:$VERSION" >/dev/null 2>&1; then echo 'Tag exists; use a new VERSION'; exit 1; fi
 skopeo copy --dest-tls-verify=false "docker-archive:$REPORTS/$svc-optimized.tar" "docker://127.0.0.1:15000/$svc:$VERSION"
 digest=$(skopeo inspect --tls-verify=false --format '{{.Digest}}' "docker://127.0.0.1:15000/$svc:$VERSION")
 [[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]
 # Test the exact endpoint used by kubelet, including HTTP runtime configuration.
 minikube -p "$PROFILE" ssh -- "sudo crictl pull localhost:5000/$svc@$digest"
 printf 'image:\n  digest: %s\nappVersion: "%s"\n' "$digest" "$VERSION" > "$REPORTS/$svc-image.yaml"
done
curl -fsS http://127.0.0.1:15000/v2/_catalog > "$REPORTS/registry-catalog.json"
