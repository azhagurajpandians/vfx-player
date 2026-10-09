#!/usr/bin/env bash
# ==============================================================================
# VFX Review Player - macOS Build Script (.app, .dmg, .zip)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VERSION="1.1.4"
if [ -f "VERSION" ]; then
    VERSION="$(tr -d '[:space:]' < VERSION)"
fi

ARCH="$(python3 -c 'import platform; print(platform.machine())' 2>/dev/null || uname -m)"
if [ -z "$ARCH" ]; then
    ARCH="$(uname -m)"
fi

echo "========================================================"
echo "        VFX Review Player - macOS Distribution Build    "
echo "                   Version: ${VERSION}                  "
echo "              Architecture: ${ARCH}                     "
echo "========================================================"

# Ensure python3 is available
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 command not found. Please install Python 3.10+."
    exit 1
fi

echo "[INFO] Using Python: $(python3 --version)"

# Ensure logo.icns exists
if [ ! -f "logo.icns" ]; then
    echo "[INFO] Generating logo.icns from logo.png..."
    python3 -c "
try:
    from PIL import Image
    img = Image.open('logo.png')
    img.save('logo.icns', format='ICNS')
    print('Generated logo.icns using Pillow.')
except Exception as e:
    print(f'Pillow ICNS generation skipped: {e}')
" || true
fi

# Clean old build artifacts
echo "[INFO] Cleaning old build directories..."
rm -rf build dist dist_macos dmg_staging
mkdir -p dist_macos

# Build macOS .app bundle via PyInstaller
echo "[INFO] Building macOS Application Bundle with PyInstaller..."
python3 -m PyInstaller vfx_player_mac.spec --clean --noconfirm

APP_PATH="dist/VFX Player.app"
if [ ! -d "$APP_PATH" ]; then
    echo "[ERROR] Application bundle not found at $APP_PATH! Build failed."
    exit 1
fi

# Ensure executable permissions inside Contents/MacOS
if [ -d "$APP_PATH/Contents/MacOS" ]; then
    chmod +x "$APP_PATH/Contents/MacOS/"*
    if [ -f "$APP_PATH/Contents/MacOS/VFX Player" ] && [ ! -f "$APP_PATH/Contents/MacOS/vfx-player" ]; then
        ln -sf "VFX Player" "$APP_PATH/Contents/MacOS/vfx-player"
    fi
fi

# Ad-hoc sign the application bundle (essential for Apple Silicon arm64 execution)
echo "[INFO] Signing application bundle (ad-hoc)..."
if command -v codesign &> /dev/null; then
    codesign --force --deep --sign - "$APP_PATH" || true
    echo "[INFO] Code signature applied."
fi

# Package 1: Standalone ZIP
ZIP_NAME="VFX_Player-v${VERSION}-mac-${ARCH}.zip"
echo "[INFO] Creating release ZIP: dist_macos/${ZIP_NAME}..."
if command -v ditto &> /dev/null; then
    ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "dist_macos/${ZIP_NAME}"
else
    (cd dist && zip -r -q "../dist_macos/${ZIP_NAME}" "VFX Player.app")
fi

# Package 2: Drag-and-drop DMG Installer
DMG_NAME="VFX_Player-v${VERSION}-mac-${ARCH}.dmg"
echo "[INFO] Building drag-and-drop DMG: dist_macos/${DMG_NAME}..."
mkdir -p dmg_staging
cp -R "$APP_PATH" dmg_staging/
ln -s /Applications dmg_staging/Applications

if command -v hdiutil &> /dev/null; then
    hdiutil create \
        -volname "VFX Player" \
        -srcfolder dmg_staging \
        -ov \
        -format UDZO \
        "dist_macos/${DMG_NAME}"
    echo "[INFO] DMG successfully created."
else
    echo "[WARNING] hdiutil not found, skipping DMG creation."
fi
rm -rf dmg_staging

echo "========================================================"
echo "                 macOS Build Successful!                "
echo "========================================================"
echo "Application Bundle : ${APP_PATH}"
echo "Release Artifacts  : dist_macos/"
ls -lh dist_macos/
echo "========================================================"
