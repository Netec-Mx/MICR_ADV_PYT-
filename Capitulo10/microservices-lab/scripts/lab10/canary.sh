#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
k apply -f istio/routes-90-10.yaml
sleep 5
"$PYTHON_BIN" scripts/lab10/traffic.py warmup --seconds 45
for pair in '90 10' '50 50' '0 100'; do
 read -r v1 v2 <<< "$pair"
 k apply -f "istio/routes-$v1-$v2.yaml"
 # Wait for Envoy configuration acknowledgement; record a bounded convergence pause.
 i proxy-status > "reports/lab10/proxy-status-$v1-$v2.txt"
 sleep 5
 "$PYTHON_BIN" scripts/lab10/traffic.py canary --v2-percent "$v2" --requests 400
done
"$PYTHON_BIN" scripts/lab10/traffic.py bluegreen
