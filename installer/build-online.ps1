param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    & $Python -c "from PyQt6.QtWidgets import QApplication"
    if ($LASTEXITCODE -ne 0) { throw 'Build environment needs PyInstaller and PyQt6.' }
    & $Python installer/build_bootstrap.py
    if ($LASTEXITCODE -ne 0) { throw 'Online Setup build failed.' }
    $package = Join-Path $projectRoot 'dist\ULTRON-Setup.exe'
    $hash = (Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText((Join-Path $projectRoot 'dist\ULTRON-Setup.exe.sha256'), "$hash  ULTRON-Setup.exe`n")
    Write-Output $package
} finally { Pop-Location }
