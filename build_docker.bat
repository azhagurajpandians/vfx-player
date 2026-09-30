@echo off
setlocal enabledelayedexpansion
title Build VFX Review Player Linux Package via Docker

echo ========================================================
echo     Building VFX Review Player for Linux via Docker
echo ========================================================

rem Verify Docker is installed and running
where docker >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not installed or not in PATH!
    echo Please install Docker Desktop for Windows or build using GitHub Actions / WSL.
    pause
    exit /b 1
)

docker info >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Docker daemon is not running. Please start Docker Desktop first.
    pause
    exit /b 1
)

if not exist "dist_linux" mkdir "dist_linux"

echo [INFO] Building Linux Docker container image...
docker build -t vfx-player-linux-builder -f Dockerfile.linux .

if %errorlevel% neq 0 (
    echo [ERROR] Docker build failed!
    pause
    exit /b 1
)

echo [INFO] Running container and extracting compiled Linux packages...
docker run --rm -v "%cd%\dist_linux:/output" vfx-player-linux-builder

echo ========================================================
echo     Linux Build Complete!
echo ========================================================
echo Packages saved in: %cd%\dist_linux\
dir dist_linux
echo ========================================================
pause
