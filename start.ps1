# VCClient Launch Script for PowerShell
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location "$scriptDir"
Write-Host "Starting VCClient v2.0.78-beta (pure-ONNX) on RTX 4090..." -ForegroundColor Green
& "$scriptDir\.venv\Scripts\python.exe" main.py cui --launch_client True
