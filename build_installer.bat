@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo      Building VFX Review Player Compact Installer
echo ========================================================

rem 1. Locate PyInstaller
where pyinstaller >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller not found in PATH.
    pause
    exit /b 1
)

rem 2. Locate Inno Setup Compiler (ISCC.exe)
set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC_PATH%" (
    echo [ERROR] Inno Setup Compiler not found at: "%ISCC_PATH%"
    pause
    exit /b 1
)

rem 3. Clean previous build artifacts
echo [INFO] Cleaning build, dist, and dist_installer folders...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "dist_installer" rmdir /s /q "dist_installer"

rem 4. Run PyInstaller
echo.
echo [INFO] Step 1/2: Packaging VFX Review Player with PyInstaller...
pyinstaller "vfx_review_player.spec" --clean --noconfirm

if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller packaging failed!
    pause
    exit /b 1
)

rem 5. Run Inno Setup Compiler
echo.
echo [INFO] Step 2/2: Compiling compact setup executable with Inno Setup...
"%ISCC_PATH%" "installer.iss"

if %errorlevel% neq 0 (
    echo [ERROR] Inno Setup compilation failed!
    pause
    exit /b 1
)

echo.
echo ========================================================
echo      Installer Build Successful!
echo ========================================================
echo Setup Executable: dist_installer\VFX_Review_Player_Setup_v1.0.0.exe
echo.
pause
