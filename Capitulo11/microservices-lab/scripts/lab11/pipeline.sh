#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
: "${GITOPS_DIR:?Path to clean GitOps clone}"
: "${IMAGE_REPOSITORY:?ghcr.io/owner/lab11-order-service}"
: "${APP_VERSION:=11.0.0}"
[[ -z $(git status --porcelain) ]] || { echo 'Commit application changes first'; exit 1; }
APP_SHA=$(git rev-parse HEAD)
[[ $(git branch --show-current) == main ]] || { echo 'Publish only from main'; exit 1; }
bash scripts/lab11/ci-tests.sh
"$PYTHON_BIN" scripts/lab11/gitops.py render "$GITOPS_DIR"
docker build --build-arg APP_VERSION="$APP_VERSION" --label "org.opencontainers.image.revision=$APP_SHA" --tag "$IMAGE_REPOSITORY:$APP_SHA" -f order-service/Dockerfile .
docker save "$IMAGE_REPOSITORY:$APP_SHA" -o reports/lab11/order-service.tar
# Gate all CRITICAL vulnerabilities, including unfixed; no .trivyignore bypass.
trivy image --input reports/lab11/order-service.tar --scanners vuln --severity CRITICAL --ignorefile /dev/null --format json --output reports/lab11/trivy.json --exit-code 1
docker push "$IMAGE_REPOSITORY:$APP_SHA" | tee reports/lab11/push.txt
DIGEST=$(sed -nE 's/.*digest: (sha256:[a-f0-9]{64}).*/\1/p' reports/lab11/push.txt | tail -1)
[[ $DIGEST =~ ^sha256:[a-f0-9]{64}$ ]] || { echo 'Missing registry digest'; exit 1; }
"$PYTHON_BIN" scripts/lab11/gitops.py update "$GITOPS_DIR" "$IMAGE_REPOSITORY" "$DIGEST" "$APP_VERSION" "$APP_SHA" | tee reports/lab11/gitops-update.txt
git -C "$GITOPS_DIR" rev-parse HEAD > reports/lab11/published-gitops-sha.txt
