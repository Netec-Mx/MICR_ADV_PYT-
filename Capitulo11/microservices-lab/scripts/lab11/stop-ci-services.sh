#!/usr/bin/env bash
set -euo pipefail
for name in lab11-ci-postgres lab11-ci-redis lab11-ci-keycloak; do
 docker rm -f "$name" >/dev/null 2>&1 || true
done
