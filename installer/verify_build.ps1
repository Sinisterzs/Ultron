param([string]$Python = 'python', [switch]$Build)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if ($Build) {
        & $Python -X utf8 installer/build_bootstrap.py
        if ($LASTEXITCODE -ne 0) { throw 'Setup compilation failed.' }
    }
    $checkRoot = Join-Path $projectRoot '.installer-checks'
    $output = Join-Path $checkRoot ('exe-verified-' + [Guid]::NewGuid().ToString('N'))
    $env:ULTRON_DATA_DIR = Join-Path $checkRoot 'smoke-user'
    $setup = Join-Path $projectRoot 'dist\ULTRON-Setup.exe'
    $process = Start-Process -FilePath $setup -ArgumentList @('--smoke-test', $output) -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(45000)) {
        $process.Kill($true)
        throw 'Headless setup verification timed out.'
    }
    if ($process.ExitCode -ne 0) {
        Get-Content -LiteralPath (Join-Path $output 'error.txt') -ErrorAction SilentlyContinue
        throw 'Headless setup verification failed.'
    }
    Get-Content -LiteralPath (Join-Path $output 'report.json')
    & $Python -X utf8 -m unittest discover -s tests -p 'test_*.py' -q
    if ($LASTEXITCODE -ne 0) { throw 'Regression tests failed.' }
    & $Python tools/render_setup_preview.py
    if ($LASTEXITCODE -ne 0) { throw 'Preview render failed.' }
    $hash = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText((Join-Path $projectRoot 'dist\ULTRON-Setup.exe.sha256'), "$hash  ULTRON-Setup.exe`n")
    Write-Output 'Setup verified without installation, voice, credentials or network.'
} finally { Pop-Location }
