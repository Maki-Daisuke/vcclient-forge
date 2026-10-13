# VCClient Launch Script for PowerShell
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$scriptDir"
Write-Host "Starting VCClient v2.0.78-beta (pure-ONNX)..." -ForegroundColor Green

if (Test-Path "$scriptDir\runtime\Scripts\python.exe") {
    & "$scriptDir\runtime\Scripts\python.exe" main.py cui --launch_client True
} elseif (Test-Path "$scriptDir\.venv\Scripts\python.exe") {
    & "$scriptDir\.venv\Scripts\python.exe" main.py cui --launch_client True
} else {
    uv run python main.py cui --launch_client True
}
