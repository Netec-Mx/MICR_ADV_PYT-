#!/usr/bin/env bash
set -euo pipefail
case "$(uname -m)" in x86_64) arch=amd64;; aarch64) arch=arm64;; *) exit 1;; esac
TASK_TMP=$(mktemp -d); trap 'rm -rf "$TASK_TMP"' EXIT
name="istio-1.31.1-linux-$arch.tar.gz"
url=https://github.com/istio/istio/releases/download/1.31.1
curl -fsSL "$url/$name" -o "$TASK_TMP/$name"
curl -fsSL "$url/$name.sha256" -o "$TASK_TMP/$name.sha256"
(cd "$TASK_TMP"; sha256sum -c "$name.sha256")
tar -xzf "$TASK_TMP/$name" -C "$TASK_TMP"
mkdir -p "$HOME/.local/bin"
install -m 755 "$TASK_TMP/istio-1.31.1/bin/istioctl" "$HOME/.local/bin/istioctl"
"$HOME/.local/bin/istioctl" version --remote=false
