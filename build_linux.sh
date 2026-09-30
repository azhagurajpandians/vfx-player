#!/usr/bin/env bash
# ==============================================================================
# VFX Review Player - Linux Build Script (cx_Freeze / PyInstaller)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VERSION="1.1.4"
if [ -f "VERSION" ]; then
    VERSION="$(tr -d '[:space:]' < VERSION)"
fi

echo "========================================================"
echo "       VFX Review Player - Linux Distribution Build      "
echo "                   Version: ${VERSION}                  "
echo "========================================================"

BUILD_METHOD="${1:-cxfreeze}"

# Ensure python is available
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 command not found. Please install Python 3.10 or 3.11."
    exit 1
fi

echo "[INFO] Using Python: $(python3 --version)"

# Clean previous build artifacts
echo "[INFO] Cleaning old build directories..."
rm -rf build dist dist_linux
mkdir -p dist_linux

if [ "$BUILD_METHOD" = "pyinstaller" ]; then
    echo "[INFO] Building with PyInstaller using vfx_player_linux.spec..."
    pyinstaller vfx_player_linux.spec --clean --noconfirm
    OUTPUT_DIR="dist/vfx-player"
    EXE_FILE="${OUTPUT_DIR}/vfx-player"
else
    echo "[INFO] Building with cx_Freeze (python3 setup.py build)..."
    python3 setup.py build
    OUTPUT_DIR="$(find build -maxdepth 1 -type d -name "exe.linux*" | head -n 1)"
    EXE_FILE="${OUTPUT_DIR}/vfx-player"
fi

if [ ! -f "$EXE_FILE" ]; then
    echo "[ERROR] Executable not found at $EXE_FILE! Build failed."
    exit 1
fi

chmod +x "$EXE_FILE"

# Copy desktop and icon assets to the output directory
cp logo.png "${OUTPUT_DIR}/vfx-player.png"
cp vfx-player.desktop "${OUTPUT_DIR}/"

# Package into tar.gz
ARCHIVE_NAME="vfx-player-v${VERSION}-linux-x86_64.tar.gz"
echo "[INFO] Creating release archive: dist_linux/${ARCHIVE_NAME}..."
tar -czf "dist_linux/${ARCHIVE_NAME}" -C "$(dirname "${OUTPUT_DIR}")" "$(basename "${OUTPUT_DIR}")"

ARCHIVE_SIZE="$(du -h "dist_linux/${ARCHIVE_NAME}" | cut -f1)"

echo "========================================================"
echo "                 Build Successful!                      "
echo "========================================================"
echo "Output Directory : ${OUTPUT_DIR}"
echo "Release Archive  : dist_linux/${ARCHIVE_NAME} (${ARCHIVE_SIZE})"
echo "Run application  : ${EXE_FILE}"
echo "========================================================"
