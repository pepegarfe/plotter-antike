@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1"
if errorlevel 1 (
    echo.
    echo  ERROR: La instalacion fallo. Revisa el mensaje de arriba.
    pause
)
