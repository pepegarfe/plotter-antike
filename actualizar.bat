@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Plotter Antike — Actualizar y Publicar

echo.
echo  ===================================================
echo   Plotter Antike ^| Compilar, Instalar y Publicar
echo  ===================================================
echo.

echo  [1/6] Limpiando cache anterior...
if exist build\PlotterAntike rmdir /s /q build\PlotterAntike
if exist build\PlotterSTM   rmdir /s /q build\PlotterSTM
if exist dist\PlotterAntike.exe del /f /q dist\PlotterAntike.exe
echo        OK
echo.

echo  [2/6] Instalando herramientas de build...
pip install pyinstaller pillow --quiet --upgrade
if errorlevel 1 ( echo  ERROR: pip install fallo. & pause & exit /b 1 )
echo        OK
echo.

echo  [3/6] Generando icono...
python crear_icono.py
if errorlevel 1 ( echo  ERROR: No se pudo generar icon.ico. & pause & exit /b 1 )
echo.

echo  [4/6] Compilando ejecutable...
python -m PyInstaller PlotterAntike.spec --noconfirm --clean
if errorlevel 1 ( echo  ERROR: PyInstaller fallo. & pause & exit /b 1 )
echo.

echo  [5/6] Instalando localmente...
copy /Y instalar.bat "dist\instalar.bat" >nul
copy /Y instalar.ps1 "dist\instalar.ps1" >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dist\instalar.ps1"
if errorlevel 1 (
    echo  ERROR: La instalacion fallo.
    pause
    exit /b 1
)
echo.

echo  [6/6] Publicando en GitHub (inicia build automatico para Windows y Mac)...
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy.MM.dd"') do set TAG=v%%i
git tag -f "%TAG%"
git push origin "%TAG%" --force
if errorlevel 1 ( echo  ERROR: No se pudo publicar el tag en GitHub. & pause & exit /b 1 )
echo        OK
echo.

echo  ===================================================
echo   Listo!
echo.
echo   - Instalado localmente en este equipo.
echo   - Build automatico iniciado en GitHub para Windows y Mac.
echo.
echo   Ver progreso:
echo   https://github.com/pepegarfe/plotter-antike/actions
echo.
echo   Link de descarga (listo en ~5 min):
echo   https://github.com/pepegarfe/plotter-antike/releases/latest
echo  ===================================================
echo.
pause
