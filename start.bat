@echo off
cd /d "%~dp0"
echo Starting VCClient v2.0.78-beta (pure-ONNX) ...

main.exe server --launch_client True %*

if errorlevel 1 pause
