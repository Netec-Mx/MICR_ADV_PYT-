#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
KUBE_CONTEXT=${KUBE_CONTEXT:-msvc-gateway}
k() { kubectl --context "$KUBE_CONTEXT" "$@"; }
v() { k -n vault exec -i vault-0 -- env VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=lab07-operator-only vault "$@"; }
v status >/dev/null
# Dev mode already supplies secret/ as KV v2. Verify instead of silently ignoring errors.
v secrets list -format=json | python -c 'import sys,json; m=json.load(sys.stdin)["secret/"]; assert m["type"]=="kv" and m["options"]["version"]=="2"'
if ! v auth list -format=json | python -c 'import sys,json; sys.exit(0 if "kubernetes/" in json.load(sys.stdin) else 1)'; then v auth enable kubernetes >/dev/null; fi
v write auth/kubernetes/config kubernetes_host=https://kubernetes.default.svc:443 disable_local_ca_jwt=false >/dev/null
for service in order-service inventory-service users-service; do
  v policy write "$service" - < "vault/policies/$service.hcl" >/dev/null
  v write "auth/kubernetes/role/$service" bound_service_account_names="$service" bound_service_account_namespaces=microservices audience=vault token_policies="$service" token_ttl=60s token_max_ttl=300s token_no_default_policy=true >/dev/null
  # Retain rotated values when repeating bootstrap; only seed missing secrets.
  if ! v kv metadata get -format=json "secret/$service" >/dev/null 2>&1; then
    if [[ "$service" == order-service ]]; then
      v kv put "secret/$service" admin_key=lab07-order-admin database_url=postgresql+asyncpg://order_app:order_app_lab_pass@postgres:5432/eventstore_db service_client_secret=order-svc-secret-lab >/dev/null
    else
      v kv put "secret/$service" admin_key="lab07-$service-admin" >/dev/null
    fi
  fi
done
if ! v audit list -format=json | python -c 'import sys,json; sys.exit(0 if "file/" in json.load(sys.stdin) else 1)'; then
  v audit enable file file_path=/vault/audit/audit.json >/dev/null
fi
printf '%s\n' 'Vault configurado. Root sólo se usa en esta tarea de operador; nunca se inyecta en aplicaciones.'
