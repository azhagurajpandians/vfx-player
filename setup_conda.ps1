<#
Minimal PowerShell setup script for VFXPlayer conda environment.
Usage:
    ./setup_conda.ps1              # create or update env
    ./setup_conda.ps1 -Recreate    # delete then create
#>
param([switch]$Recreate)

$ErrorActionPreference = 'Stop'
Write-Host '--- VFXPlayer environment setup ---' -ForegroundColor Cyan

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Host 'Conda not found in PATH. Install Miniconda then reopen PowerShell.' -ForegroundColor Red
    exit 1
}

# Initialize conda for this session
try { $base = (& conda info --base).Trim(); $hook = Join-Path $base 'etc/profile.d/conda.ps1'; if (Test-Path $hook) { . $hook } } catch { }

$envName='vfxplayer'
$yml='environment.yml'
if (-not (Test-Path $yml)) { Write-Host "Missing $yml" -ForegroundColor Red; exit 1 }

if ($Recreate -and (conda env list | Select-String "^$envName\s")) {
    Write-Host "Removing existing env $envName" -ForegroundColor Yellow
    conda env remove -n $envName | Out-Null
}

if (-not (conda env list | Select-String "^$envName\s")) {
    Write-Host "Creating $envName" -ForegroundColor Green
    conda env create -f $yml
    if ($LASTEXITCODE -ne 0) { Write-Host 'Create failed.' -ForegroundColor Red; exit 1 }
} else {
    Write-Host "Updating $envName" -ForegroundColor Yellow
    conda env update -f $yml --prune
    if ($LASTEXITCODE -ne 0) { Write-Host 'Update failed.' -ForegroundColor Red; exit 1 }
}

Write-Host 'To run:' -ForegroundColor Magenta
Write-Host '  powershell -NoExit -Command "conda activate vfxplayer; set VFXPLAYER_ALLOW_EXR=1; python .\main.py"' -ForegroundColor DarkGray
Write-Host 'Done.' -ForegroundColor Cyan
