#!/usr/bin/env bash
set -euo pipefail
curl -fsSL https://get.helm.sh/helm-v3.16.2-linux-amd64.tar.gz | tar xz
helm registry login oci://ghcr.io/acme -u "$USER" --password-stdin <<< "$TOKEN"
helm rollback app 1 --recreate-pods
