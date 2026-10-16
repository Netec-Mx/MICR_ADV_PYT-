#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
i version --remote=false | grep -F 1.31.1 >/dev/null
for svc in "${SERVICES[@]}"; do h status "$svc" -n microservices >/dev/null; done
# Do not silently change injection settings of a previously configured namespace.
"$PYTHON_BIN" - <<'CHECK'
import json,os,subprocess
ns=json.loads(subprocess.check_output(['kubectl','--context',os.environ.get('KUBE_CONTEXT','msvc-gateway'),'get','ns','microservices','-o','json']))
labels=ns['metadata'].get('labels',{})
assert 'istio-injection' not in labels and 'istio.io/rev' not in labels,'Remove/resolve previous namespace-wide injection before the lab'
CHECK
i x precheck
i install -f istio/install.yaml -y
k -n istio-system rollout status deployment/istiod --timeout=300s
k -n istio-system rollout status deployment/istio-ingressgateway --timeout=300s
# Keep the first release snapshots and revisions for cleanup/recovery.
for svc in "${SERVICES[@]}"; do
 if [[ ! -s "reports/lab10/$svc-before.json" ]]; then
  h status "$svc" -n microservices -o json > "reports/lab10/$svc-before.json"
  h get values "$svc" -n microservices --all -o json > "reports/lab10/$svc-values-before.json"
 fi
done
if [[ ! -s reports/lab10/observability-before.json ]]; then
 h status lab08-observability -n observability -o json > reports/lab10/observability-before.json
fi
printf '%s\n' 'Istio installed. Namespace untouched; only chart-selected apps will be injected.'
