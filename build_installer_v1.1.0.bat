@echo off
setlocal enabledelayedexpansion
title Build VFX Review Player v1.1.0 Installer

pushd "%~dp0"

echo ========================================================
echo   Building VFX Review Player Installer (v1.1.0)
echo ========================================================
echo Target Output: dist_installer\VFX_Review_Player_Setup_v1.1.0.exe
echo.

rem =========================================================
rem 1. Check if VFX Review Player is currently running
rem =========================================================
tasklist /fi "imagename eq VFX Review Player.exe" 2>nul | find /i "VFX Review Player.exe" >nul
if %errorlevel% equ 0 (
    echo [WARNING] "VFX Review Player.exe" is currently running!
    echo Please close it to prevent file access locks during installer creation.
    echo.
)

rem =========================================================
rem 2. Detect compiled application build directory
rem =========================================================
set "BUILD_DIR="

if "%~1"=="/rebuild" goto :do_build
if "%~1"=="-rebuild" goto :do_build
if "%~1"=="/build"   goto :do_build
if "%~1"=="-build"   goto :do_build

if exist "build\exe.win-amd64-3.11\VFX Review Player.exe" (
    set "BUILD_DIR=build\exe.win-amd64-3.11"
) else if exist "build\exe.win-amd64-3.10\VFX Review Player.exe" (
    set "BUILD_DIR=build\exe.win-amd64-3.10"
) else if exist "build\exe.win-amd64-3.12\VFX Review Player.exe" (
    set "BUILD_DIR=build\exe.win-amd64-3.12"
)

if not defined BUILD_DIR (
    echo [INFO] Pre-compiled build folder not found.
    goto :do_build
) else (
    echo [INFO] Found pre-compiled build: %BUILD_DIR%
    goto :find_iscc
)

:do_build
echo [INFO] Building cx_Freeze distribution using python setup.py build...
python setup.py build
if %errorlevel% neq 0 (
    echo [ERROR] Application build with cx_Freeze failed!
    pause
    popd
    exit /b 1
)

if exist "build\exe.win-amd64-3.11\VFX Review Player.exe" (
    set "BUILD_DIR=build\exe.win-amd64-3.11"
) else if exist "build\exe.win-amd64-3.10\VFX Review Player.exe" (
    set "BUILD_DIR=build\exe.win-amd64-3.10"
) else if exist "build\exe.win-amd64-3.12\VFX Review Player.exe" (
    set "BUILD_DIR=build\exe.win-amd64-3.12"
) else (
    echo [ERROR] Build completed but executable was not found in build directory.
    pause
    popd
    exit /b 1
)

rem =========================================================
rem 3. Locate Inno Setup Compiler (ISCC.exe)
rem =========================================================
:find_iscc
set "ISCC_PATH="

rem Check PATH
where iscc.exe >nul 2>nul
if %errorlevel% equ 0 (
    for /f "delims=" %%i in ('where iscc.exe') do (
        if not defined ISCC_PATH set "ISCC_PATH=%%i"
    )
)

rem Check standard Inno Setup 7 & 6 locations (User / Program Files)
if not defined ISCC_PATH if exist "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe" set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
if not defined ISCC_PATH if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "C:\Program Files\Inno Setup 7\ISCC.exe" set "ISCC_PATH=C:\Program Files\Inno Setup 7\ISCC.exe"
if not defined ISCC_PATH if exist "C:\Program Files (x86)\Inno Setup 7\ISCC.exe" set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 7\ISCC.exe"
if not defined ISCC_PATH if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

if not defined ISCC_PATH (
    echo [ERROR] Inno Setup Compiler (ISCC.exe) was not found!
    echo Please install Inno Setup from https://jrsoftware.org/isdl.php
    pause
    popd
    exit /b 1
)

echo [INFO] Inno Setup Compiler: "%ISCC_PATH%"

rem =========================================================
rem 4. Prepare dist_installer output folder
rem =========================================================
if not exist "dist_installer" (
    mkdir "dist_installer"
)

rem If zero-byte leftover exists, remove it
if exist "dist_installer\VFX_Review_Player_Setup_v1.1.0.exe" (
    for %%F in ("dist_installer\VFX_Review_Player_Setup_v1.1.0.exe") do (
        if %%~zF equ 0 del /f /q "dist_installer\VFX_Review_Player_Setup_v1.1.0.exe" 2>nul
    )
)

rem =========================================================
rem 5. Compile Installer
rem =========================================================
echo.
echo [INFO] Compiling installer executable with Inno Setup...
echo [INFO] Source folder: %BUILD_DIR%
echo.

"%ISCC_PATH%" /DAppSourceDir="%BUILD_DIR%" "installer_cxfreeze.iss"

if %errorlevel% neq 0 (
    echo.
    echo ========================================================
    echo   [ERROR] Inno Setup compilation failed!
    echo ========================================================
    pause
    popd
    exit /b 1
)

rem =========================================================
rem 6. Verification
rem =========================================================
echo.
echo ========================================================
echo      Installer Build Successful!
echo ========================================================
if exist "dist_installer\VFX_Review_Player_Setup_v1.1.0.exe" (
    for %%I in ("dist_installer\VFX_Review_Player_Setup_v1.1.0.exe") do (
        set /a sizeMB=%%~zI / 1048576
        echo Output File: %%~fI
        echo File Size  : !sizeMB! MB (%%~zI bytes)
        echo Timestamp  : %%~tI
    )
) else (
    echo [WARNING] Compilation reported success but setup file not found.
)
echo ========================================================
echo.

popd
pause
