@echo off
cd /d "%~dp0"
echo Starting VCClient Forge...

start /b "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:18888/"
main.exe %*

if errorlevel 1 pause
