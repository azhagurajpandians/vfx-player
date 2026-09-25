@echo off
setlocal enabledelayedexpansion
title Build VFX Review Player Installer

pushd "%~dp0"

echo ========================================================
echo        VFX Review Player Installer Builder
echo ========================================================

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
rem 2. Version Management (Reads & Auto-increments from VERSION)
rem =========================================================
set "VERSION_FILE=VERSION"
set "DO_REBUILD=0"
set "DO_BUMP=1"
set "CUSTOM_VERSION="

rem Parse command-line arguments
for %%A in (%*) do (
    if /i "%%~A"=="/rebuild" (
        set "DO_REBUILD=1"
    ) else if /i "%%~A"=="-rebuild" (
        set "DO_REBUILD=1"
    ) else if /i "%%~A"=="/build" (
        set "DO_REBUILD=1"
    ) else if /i "%%~A"=="-build" (
        set "DO_REBUILD=1"
    ) else if /i "%%~A"=="/nobump" (
        set "DO_BUMP=0"
    ) else if /i "%%~A"=="--nobump" (
        set "DO_BUMP=0"
    ) else if /i "%%~A"=="--no-bump" (
        set "DO_BUMP=0"
    ) else (
        rem Check if argument looks like a version number (contains dots)
        echo %%~A | findstr /r "^[0-9][0-9]*\.[0-9][0-9]*" >nul
        if !errorlevel! equ 0 (
            set "CUSTOM_VERSION=%%~A"
        )
    )
)

rem Read baseline version from file, default to 1.1.0 if missing
if not exist "%VERSION_FILE%" (
    echo 1.1.0> "%VERSION_FILE%"
)
set /p CURRENT_VERSION=<"%VERSION_FILE%"
rem Trim any stray whitespace
set "CURRENT_VERSION=%CURRENT_VERSION: =%"

if defined CUSTOM_VERSION (
    set "TARGET_VERSION=%CUSTOM_VERSION%"
    echo [INFO] Using custom specified version: !TARGET_VERSION!
) else if "!DO_BUMP!"=="1" (
    for /f "tokens=1,2,3 delims=." %%a in ("%CURRENT_VERSION%") do (
        set "V_MAJOR=%%a"
        set "V_MINOR=%%b"
        set "V_PATCH=%%c"
    )
    if not defined V_PATCH set "V_PATCH=0"
    set /a NEW_PATCH=V_PATCH+1
    set "TARGET_VERSION=!V_MAJOR!.!V_MINOR!.!NEW_PATCH!"
    echo [INFO] Auto-incrementing version: %CURRENT_VERSION% -^> !TARGET_VERSION!
) else (
    set "TARGET_VERSION=%CURRENT_VERSION%"
    echo [INFO] Keeping current version: !TARGET_VERSION!
)

echo [INFO] Target installer: dist_installer\VFX_Review_Player_Setup_v!TARGET_VERSION!.exe
echo.

rem =========================================================
rem 3. Detect / Rebuild Application Distribution
rem =========================================================
set "BUILD_DIR="

if "!DO_REBUILD!"=="1" goto :do_build

if exist "build\exe.win-amd64-3.11\VFX Review Player.exe" (
    set "BUILD_DIR=build\exe.win-amd64-3.11"
) else if exist "build\exe.win-amd64-3.10\VFX Review Player.exe" (
    set "BUILD_DIR=build\exe.win-amd64-3.10"
) else if exist "build\exe.win-amd64-3.12\VFX Review Player.exe" (
    set "BUILD_DIR=build\exe.win-amd64-3.12"
)

if not defined BUILD_DIR (
    echo [INFO] Pre-compiled application build not found. Running build now...
    goto :do_build
) else (
    echo [INFO] Found existing application build: %BUILD_DIR%
    goto :find_iscc
)

:do_build
echo [INFO] Building cx_Freeze distribution (python setup.py build)...
python setup.py build
if %errorlevel% neq 0 (
    echo [ERROR] Application build failed!
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
    echo [ERROR] Build completed but executable was not found.
    pause
    popd
    exit /b 1
)

rem =========================================================
rem 4. Locate Inno Setup Compiler (ISCC.exe)
rem =========================================================
:find_iscc
set "ISCC_PATH="

where iscc.exe >nul 2>nul
if %errorlevel% equ 0 (
    for /f "delims=" %%i in ('where iscc.exe') do (
        if not defined ISCC_PATH set "ISCC_PATH=%%i"
    )
)

if not defined ISCC_PATH if exist "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe" set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
if not defined ISCC_PATH if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "C:\Program Files\Inno Setup 7\ISCC.exe" set "ISCC_PATH=C:\Program Files\Inno Setup 7\ISCC.exe"
if not defined ISCC_PATH if exist "C:\Program Files (x86)\Inno Setup 7\ISCC.exe" set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 7\ISCC.exe"
if not defined ISCC_PATH if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

if not defined ISCC_PATH (
    echo [ERROR] Inno Setup Compiler ISCC.exe was not found!
    echo Please install Inno Setup from https://jrsoftware.org/isdl.php
    pause
    popd
    exit /b 1
)

echo [INFO] Inno Setup Compiler: "%ISCC_PATH%"

rem =========================================================
rem 5. Prepare Output Directory
rem =========================================================
if not exist "dist_installer" mkdir "dist_installer"

set "TARGET_EXE=dist_installer\VFX_Review_Player_Setup_v!TARGET_VERSION!.exe"
if exist "!TARGET_EXE!" (
    for %%F in ("!TARGET_EXE!") do (
        if %%~zF equ 0 del /f /q "!TARGET_EXE!" 2>nul
    )
)

rem =========================================================
rem 6. Compile Installer with Inno Setup
rem =========================================================
echo.
echo [INFO] Compiling installer with version !TARGET_VERSION!...
echo [INFO] Source folder: %BUILD_DIR%
echo.

"%ISCC_PATH%" /DMyAppVersion="!TARGET_VERSION!" /DAppSourceDir="%BUILD_DIR%" "installer_cxfreeze.iss"

if %errorlevel% neq 0 (
    echo.
    echo ========================================================
    echo   [ERROR] Inno Setup compilation failed!
    echo ========================================================
    pause
    popd
    exit /b 1
)

rem Save new version to VERSION file upon success
echo !TARGET_VERSION!> "%VERSION_FILE%"

rem =========================================================
rem 7. Verification & Summary
rem =========================================================
echo.
echo ========================================================
echo      Installer Build Successful!
echo ========================================================
if exist "!TARGET_EXE!" (
    for %%I in ("!TARGET_EXE!") do (
        set /a sizeMB=%%~zI / 1048576
        echo Version    : !TARGET_VERSION!
        echo Output File: %%~fI
        echo File Size  : !sizeMB! MB [%%~zI bytes]
        echo Timestamp  : %%~tI
    )
) else (
    echo [WARNING] Inno Setup reported success but "!TARGET_EXE!" was not found.
)
echo ========================================================
echo Next build will auto-increment from !TARGET_VERSION!
echo.

popd
pause
