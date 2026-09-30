#!/usr/bin/env bash
# ==============================================================================
# VFX Review Player - Linux AppImage Builder
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VERSION="1.1.4"
if [ -f "VERSION" ]; then
    VERSION="$(tr -d '[:space:]' < VERSION)"
fi

echo "========================================================"
echo "          VFX Review Player - AppImage Builder          "
echo "                   Version: ${VERSION}                  "
echo "========================================================"

APP_DIR="${SCRIPT_DIR}/AppDir"
DIST_DIR="${SCRIPT_DIR}/dist_linux"

# 1. Clean previous build dirs
rm -rf "$APP_DIR" "$DIST_DIR" build dist
mkdir -p "$APP_DIR" "$DIST_DIR"

# 2. Build frozen distribution first (via cx_Freeze or PyInstaller)
echo "[INFO] Compiling application distribution..."
python3 setup.py build
COMPILED_DIR="$(find build -maxdepth 1 -type d -name "exe.linux*" | head -n 1)"

if [ -z "$COMPILED_DIR" ] || [ ! -f "${COMPILED_DIR}/vfx-player" ]; then
    echo "[ERROR] cx_Freeze build failed or executable not found."
    exit 1
fi

# 3. Assemble AppDir structure
echo "[INFO] Assembling AppDir structure..."
cp -r "${COMPILED_DIR}"/* "$APP_DIR/"

# Install desktop file and icon at AppDir root
cp vfx-player.desktop "$APP_DIR/"
cp logo.png "$APP_DIR/vfx-player.png"
cp logo.png "$APP_DIR/.DirIcon"

# Create standard AppRun launcher
cat << 'EOF' > "$APP_DIR/AppRun"
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "${0}")")"

export PATH="${HERE}:${HERE}/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/lib:${HERE}/lib64:${LD_LIBRARY_PATH:-}"
export QT_PLUGIN_PATH="${HERE}/lib/PyQt6/Qt6/plugins:${QT_PLUGIN_PATH:-}"

# Colorspace configuration
if [ -f "${HERE}/configs/ocio/config.ocio" ]; then
    export OCIO="${HERE}/configs/ocio/config.ocio"
fi

exec "${HERE}/vfx-player" "$@"
EOF

chmod +x "$APP_DIR/AppRun"
chmod +x "$APP_DIR/vfx-player"

# 4. Download appimagetool if not available
if ! command -v appimagetool &> /dev/null; then
    echo "[INFO] Downloading appimagetool..."
    wget -q -O appimagetool "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" || \
    curl -sSL -o appimagetool "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x appimagetool
    TOOL="./appimagetool"
else
    TOOL="appimagetool"
fi

# 5. Build AppImage
OUTPUT_APPIMAGE="${DIST_DIR}/VFX_Review_Player-v${VERSION}-x86_64.AppImage"
echo "[INFO] Generating AppImage package..."
ARCH=x86_64 "$TOOL" --no-appstream "$APP_DIR" "$OUTPUT_APPIMAGE"

echo "========================================================"
echo "              AppImage Build Successful!                "
echo "========================================================"
echo "Artifact: ${OUTPUT_APPIMAGE}"
du -h "${OUTPUT_APPIMAGE}"
echo "========================================================"
