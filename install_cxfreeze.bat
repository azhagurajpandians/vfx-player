@echo off
REM Install script for Knack VFX Player (cx_Freeze version)
echo ========================================================
echo      Installing Knack VFX Player
echo ========================================================

set "BUILD_DIR=%~dp0build\exe.win-amd64-3.10"
set "INSTALL_DIR=%LOCALAPPDATA%\Knack VFX Player"
set "SHORTCUT_PATH=%USERPROFILE%\Desktop\Knack VFX Player.lnk"

REM Check if build directory exists
if not exist "%BUILD_DIR%" (
    echo [ERROR] Build directory not found. Please run build_cxfreeze.bat first.
    pause
    exit /b 1
)

echo [INFO] Installing to: %INSTALL_DIR%

REM Create destination directory
echo [INFO] Creating installation directory...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

REM Copy files
echo [INFO] Copying files to %INSTALL_DIR%...
xcopy /E /I /Y "%BUILD_DIR%\*" "%INSTALL_DIR%"

REM Create desktop shortcut
echo [INFO] Creating desktop shortcut...
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\Desktop\Knack VFX Player.lnk'); $Shortcut.TargetPath = '%INSTALL_DIR%\Knack VFX Player.exe'; $Shortcut.WorkingDirectory = '%INSTALL_DIR%'; $Shortcut.IconLocation = '%INSTALL_DIR%\logo.ico'; $Shortcut.Save()"

echo ========================================================
echo      Installation Complete
echo ========================================================
echo Installed to: %INSTALL_DIR%
echo Desktop shortcut created
pause
