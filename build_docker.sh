#!/usr/bin/env bash
# ==============================================================================
# Build VFX Review Player for Linux via Docker
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker is not installed or not in PATH."
    exit 1
fi

mkdir -p dist_linux

echo "[INFO] Building Docker builder image..."
docker build -t vfx-player-linux-builder -f Dockerfile.linux .

echo "[INFO] Running container and extracting compiled Linux packages..."
docker run --rm -v "${PWD}/dist_linux:/output" vfx-player-linux-builder

echo "========================================================"
echo "               Linux Build Complete!                    "
echo "========================================================"
ls -lh dist_linux
