@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0desinstalar.ps1"
if errorlevel 1 (
    echo.
    echo  ERROR: La desinstalacion fallo. Revisa el mensaje de arriba.
    pause
)
