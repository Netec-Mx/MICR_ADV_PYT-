#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
"$PYTHON_BIN" scripts/lab10/check-sidecars.py
"$PYTHON_BIN" scripts/lab10/verify-mtls.py
bash scripts/lab10/canary.sh
# Check all version series while warm-up samples are still within the rate window.
"$PYTHON_BIN" scripts/lab10/validate-observability.py
bash scripts/lab07/check_acl.sh
"$PYTHON_BIN" scripts/lab06/validate_gateway.py
"$PYTHON_BIN" scripts/lab08/test_trace.py
"$PYTHON_BIN" scripts/lab10/validate_logs.py
"$PYTHON_BIN" scripts/lab08/test_alert.py
printf '%s\n' 'Lab10: mTLS, canary, blue/green, golden signals, Vault, JWT, business/Kafka and correlated tracing passed.'
