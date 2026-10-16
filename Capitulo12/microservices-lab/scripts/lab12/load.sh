#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%S)-$RANDOM}"
export PROFILE="${PROFILE:-smoke}"
REPORT_DIR="${REPORT_DIR:-reports/lab12/$RUN_ID}"
mkdir -p "$REPORT_DIR"
export SUMMARY_PATH="$REPORT_DIR/summary.json"
export K6_PROMETHEUS_RW_SERVER_URL="${K6_PROMETHEUS_RW_SERVER_URL:-http://localhost:9090/api/v1/write}"
export K6_PROMETHEUS_RW_TREND_STATS='p(95),p(99)'
export K6_PROMETHEUS_RW_TREND_AS_NATIVE_HISTOGRAM=false
exec k6 run -o experimental-prometheus-rw -o "json=$REPORT_DIR/samples.json" tests/load/lab12.js
