@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Plotter Antike — Actualizar

echo.
echo  ===================================================
echo   Plotter Antike ^| Compilar e Instalar
echo  ===================================================
echo.

echo  [1/5] Limpiando cache anterior...
if exist build\PlotterAntike rmdir /s /q build\PlotterAntike
if exist build\PlotterSTM   rmdir /s /q build\PlotterSTM
if exist dist\PlotterAntike.exe del /f /q dist\PlotterAntike.exe
echo        OK
echo.

echo  [2/5] Instalando herramientas de build...
pip install pyinstaller pillow --quiet --upgrade
if errorlevel 1 ( echo  ERROR: pip install fallo. & pause & exit /b 1 )
echo        OK
echo.

echo  [3/5] Generando icono...
python crear_icono.py
if errorlevel 1 ( echo  ERROR: No se pudo generar icon.ico. & pause & exit /b 1 )
echo.

echo  [4/5] Compilando ejecutable...
python -m PyInstaller PlotterAntike.spec --noconfirm --clean
if errorlevel 1 ( echo  ERROR: PyInstaller fallo. & pause & exit /b 1 )
echo.

echo  [5/5] Instalando...
copy /Y instalar.bat "dist\instalar.bat" >nul
copy /Y instalar.ps1 "dist\instalar.ps1" >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dist\instalar.ps1"
if errorlevel 1 (
    echo  ERROR: La instalacion fallo.
    pause
    exit /b 1
)

echo.
echo  ===================================================
echo   Listo. El programa instalado esta actualizado.
echo  ===================================================
echo.
pause
