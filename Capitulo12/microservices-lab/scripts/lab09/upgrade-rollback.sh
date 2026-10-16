#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
[[ "$VERSION" == 9.1.0 ]] || { echo 'Run with VERSION=9.1.0 after building/scanning/publishing 9.1.0'; exit 1; }
svc=users-service
# Record the currently DEPLOYED revision, not a hard-coded revision 1.
h status "$svc" -n microservices -o json > "$REPORTS/users-before-upgrade.json"
h get values "$svc" -n microservices --all -o json > "$REPORTS/users-values-before.json"
read -r previous previous_version < <("$PYTHON_BIN" -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["info"]["status"]=="deployed"; print(d["version"],d["config"]["appVersion"])' "$REPORTS/users-before-upgrade.json")
[[ "$previous_version" != "$VERSION" ]] || { echo 'Already 9.1.0; rollback to 9.0.0 first'; exit 1; }
h upgrade "$svc" helm/msvc-chart -n microservices -f "helm/values/$svc.yaml" -f "$REPORTS/$svc-image.yaml" --set-string resources.limits.memory=384Mi --atomic --wait --timeout=300s
"$PYTHON_BIN" scripts/lab09/verify_release.py --service "$svc" --version "$VERSION"
h history "$svc" -n microservices -o json > "$REPORTS/history-upgraded.json"
h rollback "$svc" "$previous" -n microservices --wait --timeout=300s
"$PYTHON_BIN" scripts/lab09/verify_release.py --service "$svc" --version "$previous_version"
h history "$svc" -n microservices -o json > "$REPORTS/history-rolled-back.json"
h get values "$svc" -n microservices --all -o json > "$REPORTS/users-values-rolled-back.json"
"$PYTHON_BIN" -c 'import json,sys; assert json.load(open(sys.argv[1]))==json.load(open(sys.argv[2])); print("Rollback restored ALL values")' "$REPORTS/users-values-before.json" "$REPORTS/users-values-rolled-back.json"
# A rollback creates a NEW Helm revision pointing to the former configuration/image.
printf 'Restored revision configuration %s (APP_VERSION %s). Check history.\n' "$previous" "$previous_version"
