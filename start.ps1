# VCClient Launch Script for PowerShell
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$scriptDir"
Write-Host "Starting VCClient v2.0.78-beta (pure-ONNX)..." -ForegroundColor Green

if (Test-Path "$scriptDir\runtime\Scripts\python.exe") {
    & "$scriptDir\runtime\Scripts\python.exe" backend\main.py server --launch_client True
} elseif (Test-Path "$scriptDir\backend\.venv\Scripts\python.exe") {
    & "$scriptDir\backend\.venv\Scripts\python.exe" backend\main.py server --launch_client True
} elseif (Test-Path "$scriptDir\.venv\Scripts\python.exe") {
    & "$scriptDir\.venv\Scripts\python.exe" backend\main.py server --launch_client True
} else {
    uv run --project backend python backend\main.py server --launch_client True
}
