@echo off
REM Build script for Knack VFX Player using cx_Freeze
echo ========================================================
echo      Building Knack VFX Player Distribution (cx_Freeze)
echo ========================================================

REM Clean previous builds
echo [INFO] Cleaning build directory...
if exist build rmdir /s /q build 2>nul

echo [INFO] Running cx_Freeze build...
python setup.py build

if %ERRORLEVEL% EQU 0 (
    echo ========================================================
    echo      Build Successful
    echo ========================================================
    echo output: build\exe.win-amd64-3.10\
) else (
    echo ========================================================
    echo      Build Failed
    echo ========================================================
    exit /b 1
)

pause
