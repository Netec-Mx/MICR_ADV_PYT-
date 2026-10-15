#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
trivy --version | head -1 | grep -F '0.75.0' >/dev/null
trivy image --download-db-only
TASK_TMP=$(mktemp -d)
trap 'rm -rf "$TASK_TMP"' EXIT
mkdir -p reports/lab09/dependency-review
for svc in "${SERVICES[@]}"; do
 for phase in before after; do
  lock=requirements-baseline-lock.txt
  [[ "$phase" != after ]] || lock=requirements-lock.txt
  cp "$svc/$lock" "$TASK_TMP/requirements.txt"
  trivy fs --skip-db-update --scanners vuln --format json --output "reports/lab09/dependency-review/$svc-$phase.json" "$TASK_TMP"
 done
done
printf '%s\n' 'Dependency review only. Run scan.sh for complete image OS + Python findings.'
