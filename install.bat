@echo off
set "APP_NAME=Knack VFX Player"
set "SOURCE_DIR=%~dp0dist\%APP_NAME%"
set "TARGET_DIR=%LOCALAPPDATA%\%APP_NAME%"
set "EXE_NAME=%APP_NAME%.exe"
set "SHORTCUT_PATH=%USERPROFILE%\Desktop\%APP_NAME%.lnk"
set "ICON_NAME=logo.ico"

echo ==========================================
echo      Installing %APP_NAME%
echo ==========================================

if not exist "%SOURCE_DIR%" (
    echo [ERROR] Build folder not found at:
    echo %SOURCE_DIR%
    echo.
    echo Please run 'build_dist.bat' first.
    pause
    exit /b
)

if exist "%TARGET_DIR%" (
    echo [INFO] Removing old version...
    rmdir /s /q "%TARGET_DIR%"
)

echo [INFO] Copying files to %TARGET_DIR%...
mkdir "%TARGET_DIR%"
xcopy /E /I /Q /Y "%SOURCE_DIR%" "%TARGET_DIR%"

echo ==========================================
echo      Finalizing Setup
echo ==========================================

REM Create Desktop Shortcut
echo [INFO] Creating Desktop Shortcut...
set "ICON_PATH=%TARGET_DIR%\%ICON_NAME%"

if not exist "%ICON_PATH%" (
    echo [WARNING] Icon not found in target. Using default.
    set "ICON_PATH="
)

rem PowerShell script to create shortcut
set "PS_CMD=$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT_PATH%');"
set "PS_CMD=%PS_CMD%$s.TargetPath='%TARGET_DIR%\%EXE_NAME%';"
set "PS_CMD=%PS_CMD%$s.WorkingDirectory='%TARGET_DIR%';"
if defined ICON_PATH (
    set "PS_CMD=%PS_CMD%$s.IconLocation='%ICON_PATH%,0';"
)
set "PS_CMD=%PS_CMD%$s.Save()"

powershell -NoProfile -ExecutionPolicy Bypass -Command "%PS_CMD%"

echo.
echo ==========================================
echo      Installation Complete!
echo ==========================================
echo Application installed to: %TARGET_DIR%
echo Shortcut created: %SHORTCUT_PATH%
echo.
pause
