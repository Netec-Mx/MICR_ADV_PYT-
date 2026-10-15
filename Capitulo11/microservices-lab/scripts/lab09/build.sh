#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
# Host Docker daemon; build context is the project root, not the service folder.
[[ -z "${MINIKUBE_ACTIVE_DOCKERD:-}" ]] || { echo 'Unset minikube docker-env first'; exit 1; }
docker info >/dev/null
BASELINE_IMAGE=${BASELINE_IMAGE:-python:3.12.14-bookworm}
RUNTIME_IMAGE=${RUNTIME_IMAGE:-python:3.12.14-slim-bookworm}
docker pull "$BASELINE_IMAGE"; docker pull "$RUNTIME_IMAGE"
# Resolve mutable base tags to exact digests for this comparison.
BASELINE_DIGEST=$(docker image inspect "$BASELINE_IMAGE" --format '{{index .RepoDigests 0}}')
RUNTIME_DIGEST=$(docker image inspect "$RUNTIME_IMAGE" --format '{{index .RepoDigests 0}}')
printf '%s\n%s\n' "$BASELINE_DIGEST" "$RUNTIME_DIGEST" > "$REPORTS/base-digests.txt"
base_fingerprint() { docker run --rm --entrypoint python "$1" -c 'import sys; from pathlib import Path; print(sys.version_info[:3]); print(next(x for x in Path("/etc/os-release").read_text().splitlines() if x.startswith("VERSION_ID=")))'; }
baseline_fingerprint=$(base_fingerprint "$BASELINE_DIGEST")
runtime_fingerprint=$(base_fingerprint "$RUNTIME_DIGEST")
[[ "$baseline_fingerprint" == "$runtime_fingerprint" ]] || { echo 'Baseline/runtime Python or Debian versions differ; comparison invalid'; exit 1; }
printf '%s\n' "$baseline_fingerprint" > "$REPORTS/base-versions.txt"

for svc in "${SERVICES[@]}"; do
 lock=requirements-lock.txt
 if [[ "$VERSION" == 9.0.0 ]]; then lock=requirements-baseline-lock.txt; fi
 sha256sum "$svc/$lock" > "$REPORTS/$svc-lock.sha256"
 for kind in baseline optimized; do
  file="$svc/Dockerfile"; base="$RUNTIME_DIGEST"
  if [[ "$kind" == baseline ]]; then file="$svc/Dockerfile.baseline"; base="$BASELINE_DIGEST"; fi
  tag="$svc:lab09-$kind-$VERSION"
  if docker image inspect "$tag" >/dev/null 2>&1; then echo "Refusing to overwrite $tag; use a new VERSION"; exit 1; fi
  DOCKER_BUILDKIT=1 docker build --build-arg REQUIREMENTS_LOCK="$lock" --build-arg BASE_IMAGE="$base" --build-arg APP_VERSION="$VERSION" -f "$file" -t "$tag" .
  docker image inspect "$tag" > "$REPORTS/$svc-$kind-inspect.json"
  docker save "$tag" -o "$REPORTS/$svc-$kind.tar"
 done
 docker run --rm --entrypoint python "$svc:lab09-optimized-$VERSION" -c 'import os,shared.vault.launcher; assert os.getuid()==10001; print("runtime imports and UID OK")'
done
"$PYTHON_BIN" scripts/lab09/report.py sizes "$REPORTS"
