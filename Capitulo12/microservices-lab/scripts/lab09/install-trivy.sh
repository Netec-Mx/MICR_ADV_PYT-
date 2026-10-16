#!/usr/bin/env bash
set -euo pipefail
case "$(uname -m)" in x86_64) arch=64bit;; aarch64) arch=ARM64;; *) echo 'Unsupported architecture'; exit 1;; esac
TASK_TMP=$(mktemp -d); trap 'rm -rf "$TASK_TMP"' EXIT
asset="trivy_0.75.0_Linux-$arch.tar.gz"
url=https://github.com/aquasecurity/trivy/releases/download/v0.75.0
curl -fsSL "$url/$asset" -o "$TASK_TMP/$asset"
curl -fsSL "$url/trivy_0.75.0_checksums.txt" -o "$TASK_TMP/checksums.txt"
(cd "$TASK_TMP"; awk -v file="$asset" '$2==file {print}' checksums.txt > selected.sha256; test -s selected.sha256; sha256sum -c selected.sha256)
tar -xzf "$TASK_TMP/$asset" -C "$TASK_TMP" trivy
mkdir -p "$HOME/.local/bin"
install -m 755 "$TASK_TMP/trivy" "$HOME/.local/bin/trivy"
"$HOME/.local/bin/trivy" --version
printf '%s\n' 'Add $HOME/.local/bin to PATH in the lab shell.'
