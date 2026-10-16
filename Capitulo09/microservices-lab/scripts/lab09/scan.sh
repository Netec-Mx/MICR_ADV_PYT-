#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
trivy --version > "$REPORTS/trivy-version.txt"
trivy --version | head -1 | grep -F '0.75.0' >/dev/null || { echo 'Use Trivy 0.75.0'; exit 1; }
trivy image --download-db-only
# Freeze one DB snapshot for the six scans; do not count table headers.
for svc in "${SERVICES[@]}"; do
 for kind in baseline optimized; do
  trivy image --skip-db-update --scanners vuln --input "$REPORTS/$svc-$kind.tar" --format json --output "$REPORTS/$svc-$kind-trivy.json" --exit-code 0
 done
done
"$PYTHON_BIN" scripts/lab09/report.py cves "$REPORTS"
