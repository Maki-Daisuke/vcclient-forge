@echo off
cd /d "%~dp0"
echo Starting VCClient v2.0.78-beta (pure-ONNX) ...

if exist "runtime\Scripts\python.exe" (
    runtime\Scripts\python.exe backend\main.py server --launch_client True
) else if exist "backend\.venv\Scripts\python.exe" (
    backend\.venv\Scripts\python.exe backend\main.py server --launch_client True
) else if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe backend\main.py server --launch_client True
) else (
    uv run --project backend python backend\main.py server --launch_client True
)

if errorlevel 1 pause
