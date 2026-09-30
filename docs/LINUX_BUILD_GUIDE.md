# VFX Review Player - Linux Build & Deployment Guide

This guide provides instructions for building, packaging, and deploying **VFX Review Player** on Linux systems (Ubuntu, Debian, Rocky Linux, AlmaLinux, RHEL, CentOS, Fedora, and Arch).

---

## Table of Contents
1. [Overview](#1-overview)
2. [Method 1: Cloud Build via GitHub Actions (Zero Setup)](#2-method-1-cloud-build-via-github-actions-zero-setup)
3. [Method 2: One-Click Docker Build (Windows or Linux)](#3-method-2-one-click-docker-build-windows-or-linux)
4. [Method 3: Native Linux Build (Workstations & Render Nodes)](#4-method-3-native-linux-build-workstations--render-nodes)
5. [Method 4: Windows Subsystem for Linux (WSL 2)](#5-method-4-windows-subsystem-for-linux-wsl-2)
6. [Desktop Integration & File Associations](#6-desktop-integration--file-associations)

---

## 1. Overview

VFX Review Player supports two distribution formats on Linux:

| Format | Output Artifact | Best For |
|---|---|---|
| **AppImage** | `VFX_Review_Player-v1.1.4-x86_64.AppImage` | Single-file portable executable that runs across all Linux distributions without installation or root privileges. |
| **Standalone Tarball** | `vfx-player-v1.1.4-linux-x86_64.tar.gz` | Studio shared server deployments, pipeline mounts (e.g. `/opt/knack/vfx-player` or `/mnt/pipeline/bin`), and custom wrapper launchers. |

---

## 2. Method 1: Cloud Build via GitHub Actions (Zero Setup)

If you are developing on Windows and do not have Linux or Docker installed locally, you can use the automated GitHub Actions workflow:

1. Push your repository to GitHub or create a release tag (e.g. `v1.1.4`).
2. Go to the **Actions** tab in your GitHub repository.
3. Select the **Build Linux Packages** workflow from the left sidebar.
4. Click **Run workflow** -> Select `main` -> Click **Run workflow**.
5. Once completed, download the generated artifacts:
   - `VFX_Review_Player-v1.1.4-x86_64.AppImage`
   - `vfx-player-v1.1.4-linux-x86_64.tar.gz`

---

## 3. Method 2: One-Click Docker Build (Windows or Linux)

You can build the Linux binary directly from Windows using Docker Desktop:

### On Windows:
```cmd
build_docker.bat
```

### On Linux or macOS:
```bash
docker build -t vfx-player-linux-builder -f Dockerfile.linux .
docker run --rm -v "$(pwd)/dist_linux:/output" vfx-player-linux-builder
```

The resulting AppImage and `.tar.gz` archives will appear in your local `dist_linux/` directory.

---

## 4. Method 3: Native Linux Build (Workstations & Render Nodes)

### Prerequisites

#### Ubuntu / Debian / Linux Mint:
```bash
sudo apt-get update
sudo apt-get install -y \
  python3 python3-pip python3-venv python3-dev \
  build-essential ffmpeg \
  libgl1-mesa-dev libgl1-mesa-glx libegl1-mesa-dev libglu1-mesa-dev \
  libglib2.0-0 libfontconfig1 libfreetype6 \
  libxcb-xinerama0 libxcb-cursor0 libxkbcommon-x11-0 libdbus-1-3 libfuse2 \
  wget curl file
```

#### Rocky Linux 8/9 / AlmaLinux / CentOS Stream / RHEL:
```bash
sudo dnf install -y epel-release
sudo dnf config-manager --set-enabled crb || sudo dnf config-manager --set-enabled powertools
sudo dnf install -y \
  python3 python3-pip python3-devel \
  gcc gcc-c++ make ffmpeg \
  mesa-libGL-devel mesa-libEGL-devel mesa-libGLU-devel \
  glib2 fontconfig freetype \
  xcb-util-cursor libxkbcommon-x11 fuse-libs \
  wget curl file
```

### Build Steps

```bash
# 1. Clone or navigate to the repository
git clone https://github.com/azhagurajpandians/vfx-player.git
cd vfx-player

# 2. (Optional) Set up Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip setuptools wheel
pip install -r requirements-linux.txt

# 4. Build Standalone Distribution & Tarball
chmod +x build_linux.sh
./build_linux.sh

# 5. Build Portable AppImage
chmod +x build_appimage.sh
./build_appimage.sh
```

Artifacts will be placed in `dist_linux/`:
- `dist_linux/VFX_Review_Player-v1.1.4-x86_64.AppImage`
- `dist_linux/vfx-player-v1.1.4-linux-x86_64.tar.gz`

---

## 5. Method 4: Windows Subsystem for Linux (WSL 2)

If you have Windows 10/11:
1. Open PowerShell as Administrator and run:
   ```powershell
   wsl --install -d Ubuntu
   ```
2. Restart your computer if prompted.
3. Open the Ubuntu terminal and navigate to your Windows drive:
   ```bash
   cd /mnt/e/exrtojpg/VFXPlayer
   ```
4. Run the steps in [Method 3: Native Linux Build](#4-method-3-native-linux-build-workstations--render-nodes).

---

## 6. Desktop Integration & File Associations

### Running the AppImage
```bash
chmod +x VFX_Review_Player-v1.1.4-x86_64.AppImage
./VFX_Review_Player-v1.1.4-x86_64.AppImage
```

### Installing Desktop Entry and File Associations
To integrate VFX Review Player into your desktop application menu (GNOME, KDE, XFCE) and associate VFX formats (`.exr`, `.dpx`, `.cin`, `.mov`, `.mp4`):

```bash
# Copy binary / AppImage to user local bin
mkdir -p ~/.local/bin
cp VFX_Review_Player-v1.1.4-x86_64.AppImage ~/.local/bin/vfx-player
chmod +x ~/.local/bin/vfx-player

# Install icon
mkdir -p ~/.local/share/icons/hicolor/256x256/apps
cp logo.png ~/.local/share/icons/hicolor/256x256/apps/vfx-player.png

# Install desktop shortcut
mkdir -p ~/.local/share/applications
cp vfx-player.desktop ~/.local/share/applications/

# Update desktop and MIME database
update-desktop-database ~/.local/share/applications/
```
