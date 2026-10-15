#!/usr/bin/env bash
set -euo pipefail
case "$(uname -m)" in x86_64) arch=amd64;; aarch64) arch=arm64;; *) exit 1;; esac
TASK_TMP=$(mktemp -d); trap 'rm -rf "$TASK_TMP"' EXIT
asset="helm-v3.20.1-linux-$arch.tar.gz"
curl -fsSL "https://get.helm.sh/$asset" -o "$TASK_TMP/$asset"
curl -fsSL "https://get.helm.sh/$asset.sha256sum" -o "$TASK_TMP/check.sha256"
(cd "$TASK_TMP"; sha256sum -c check.sha256)
tar -xzf "$TASK_TMP/$asset" -C "$TASK_TMP"
mkdir -p "$HOME/.local/bin"
install -m 755 "$TASK_TMP/linux-$arch/helm" "$HOME/.local/bin/helm"
