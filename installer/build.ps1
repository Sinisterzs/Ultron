param(
    [string]$Python = "python",
    [string]$Iscc = "",
    [switch]$AppOnly
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    # The Python environment must already contain the application's requirements.
    & $Python -c "import PyInstaller, PyQt6, numpy, sounddevice; from google import genai"
    if ($LASTEXITCODE -ne 0) { throw 'Use an environment with requirements.txt and PyInstaller installed.' }
    & $Python -m PyInstaller --noconfirm installer/ULTRON.spec
    if ($LASTEXITCODE -ne 0) { throw 'Application build failed.' }
    if ($AppOnly) { return }
    if (-not $Iscc) {
        $compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($compiler) { $Iscc = $compiler.Source }
        else { $Iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe' }
    }
    if (-not (Test-Path -LiteralPath $Iscc)) { throw 'Inno Setup compiler not found. Pass -Iscc with its path.' }
    & $Iscc installer/setup.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
} finally { Pop-Location }
