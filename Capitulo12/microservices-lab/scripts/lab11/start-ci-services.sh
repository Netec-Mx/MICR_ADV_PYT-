#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
mkdir -p .ci-state
"$PYTHON_BIN" - <<'PYCODE'
import yaml,json
from pathlib import Path
obj=yaml.safe_load(Path('k8s/lab06/03-keycloak-realm.yaml').read_text())
realm=json.loads(obj['data']['microservices-lab-realm.json'])
# The actual tests require the same identity contract and a short-expiry client.
expiry=next(c for c in realm['clients'] if c['clientId']=='expiry-test-client')
expiry['attributes']['access.token.lifespan']='2'
Path('.ci-state/microservices-lab-realm.json').write_text(json.dumps(realm))
PYCODE
# Isolated container names and ports; never use the classroom databases.
docker run -d --name lab11-ci-postgres -p 127.0.0.1:15432:5432 -e POSTGRES_PASSWORD=lab11-ci-pass postgres:16.4-bookworm
docker run -d --name lab11-ci-redis -p 127.0.0.1:16379:6379 redis:7.2.5-alpine
docker run -d --name lab11-ci-keycloak -p 127.0.0.1:18081:8080 -v "$ROOT/.ci-state:/opt/keycloak/data/import:ro" quay.io/keycloak/keycloak:26.8.0 start-dev --import-realm --hostname=http://localhost:18081
"$PYTHON_BIN" - <<'PYCODE'
import time,subprocess,urllib.request
end=time.monotonic()+240
while time.monotonic()<end:
    pg=subprocess.run(['docker','exec','lab11-ci-postgres','pg_isready','-U','postgres'],capture_output=True).returncode==0
    redis=subprocess.run(['docker','exec','lab11-ci-redis','redis-cli','ping'],capture_output=True).returncode==0
    try:
        with urllib.request.urlopen('http://localhost:18081/realms/microservices-lab/.well-known/openid-configuration',timeout=2) as x:kc=x.status==200
    except Exception:kc=False
    if pg and redis and kc:break
    time.sleep(2)
else:raise RuntimeError('Isolated CI dependencies did not become ready')
PYCODE

docker exec lab11-ci-postgres psql -U postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE order_app LOGIN PASSWORD 'order_app_lab_pass'"
