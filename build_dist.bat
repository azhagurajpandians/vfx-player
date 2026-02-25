@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo      Building Knack VFX Player Distribution
echo ========================================================

rem 1. Check if PyInstaller is available
where pyinstaller >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller not found in PATH.
    echo Please ensure you have installed requirements: pip install -r requirements.txt
    pause
    exit /b 1
)

rem 2. Clean previous build artifacts
if exist "build" (
    echo [INFO] Cleaning build directory...
    rmdir /s /q "build"
)
if exist "dist" (
    echo [INFO] Cleaning dist directory...
    rmdir /s /q "dist"
)

rem 3. Run PyInstaller
echo [INFO] Running PyInstaller...
pyinstaller "Knack VFX Player.spec" --clean --noconfirm

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed! Check the output above for errors.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo      Build Successful!
echo ========================================================
echo output: dist\Knack VFX Player\
echo.
pause
