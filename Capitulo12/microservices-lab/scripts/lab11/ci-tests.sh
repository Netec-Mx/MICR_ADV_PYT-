#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
: "${POSTGRES_TEST_ADMIN_URL:?Set isolated PostgreSQL admin URL}"
: "${REDIS_TEST_URL:?Set isolated Redis URL}"
: "${KEYCLOAK_TEST_ISSUER:?Set isolated Keycloak test issuer}"
# Coverage includes all Orders application modules; no service-module exclusions.
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
cd order-service
"$PYTHON_BIN" -m pytest tests --cov=app --cov-report=term-missing --cov-report=xml:"$ROOT/reports/lab11/coverage.xml" --cov-fail-under=80 --junitxml="$ROOT/reports/lab11/tests.xml" -q

"$PYTHON_BIN" - <<'PYCODE'
import xml.etree.ElementTree as ET
from pathlib import Path
root=ET.parse(Path('../reports/lab11/tests.xml')).getroot()
assert sum(int(s.get('skipped','0')) for s in root.iter('testsuite'))==0,'CI cannot pass with skipped integration tests'
PYCODE
