@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo      Building VFX Review Player Installer (cx_Freeze Build)
echo ========================================================

rem 1. Check if build directory exists
set "BUILD_DIR=%~dp0build\exe.win-amd64-3.11"
if not exist "%BUILD_DIR%" (
    set "BUILD_DIR=%~dp0build\exe.win-amd64-3.10"
)
if not exist "%BUILD_DIR%" (
    echo [ERROR] Build directory not found!
    echo Please run build_cxfreeze.bat first.
    pause
    exit /b 1
)

rem 2. Locate Inno Setup Compiler (ISCC.exe)
set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC_PATH%" (
    set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
)
if not exist "%ISCC_PATH%" (
    set "ISCC_PATH=C:\Users\%USERNAME%\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
)
if not exist "%ISCC_PATH%" (
    echo [ERROR] Inno Setup Compiler not found.
    pause
    exit /b 1
)

rem 3. Clean previous installer folder
if not exist "dist_installer" (
    mkdir "dist_installer"
)

rem 4. Run Inno Setup Compiler
echo.
echo [INFO] Compiling installer with Inno Setup...
"%ISCC_PATH%" "%~dp0installer_cxfreeze.iss"

if %errorlevel% neq 0 (
    echo [ERROR] Inno Setup compilation failed!
    pause
    exit /b 1
)

echo.
echo ========================================================
echo      Installer Build Successful!
echo ========================================================
echo Setup Executable: dist_installer\VFX_Review_Player_Setup_v1.1.0.exe
echo.
pause
