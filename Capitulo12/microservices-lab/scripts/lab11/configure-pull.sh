#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
read -rp 'GitHub user: ' GHCR_USER
read -rsp 'PAT classic with read:packages (not stored in Git): ' GHCR_TOKEN
printf '\n'
TASK_DOCKER_CONFIG=$(mktemp -d); chmod 700 "$TASK_DOCKER_CONFIG"
trap 'rm -rf "$TASK_DOCKER_CONFIG"; unset GHCR_TOKEN' EXIT
printf '%s' "$GHCR_TOKEN" | docker --config "$TASK_DOCKER_CONFIG" login ghcr.io -u "$GHCR_USER" --password-stdin
k -n microservices create secret generic lab11-ghcr-pull --type=kubernetes.io/dockerconfigjson --from-file=.dockerconfigjson="$TASK_DOCKER_CONFIG/config.json" --dry-run=client -o yaml | k apply -f - >/dev/null
unset GHCR_TOKEN
