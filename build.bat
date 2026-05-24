@echo off
chcp 65001 >nul
title Plotter Antike — Build

echo.
echo  ===================================================
echo   Plotter Antike ^| Build del instalador
echo  ===================================================
echo.

echo  [1/4] Instalando herramientas de build...
pip install pyinstaller pillow --quiet --upgrade
if errorlevel 1 (
    echo  ERROR: pip install fallo.
    pause & exit /b 1
)
echo        OK
echo.

echo  [2/4] Generando icono...
python crear_icono.py
if errorlevel 1 (
    echo  ERROR: No se pudo generar icon.ico.
    pause & exit /b 1
)
echo.

echo  [3/4] Compilando ejecutable (puede tardar unos minutos)...
python -m PyInstaller PlotterAntike.spec --noconfirm --clean
if errorlevel 1 (
    echo  ERROR: PyInstaller fallo.
    pause & exit /b 1
)
echo.

echo  [4/4] Copiando instalador a dist\...
copy /Y instalar.bat "dist\instalar.bat" >nul
copy /Y instalar.ps1 "dist\instalar.ps1" >nul
echo        OK
echo.

echo  ===================================================
echo   Build completado!
echo.
echo   Carpeta lista para distribuir:  dist\
echo     PlotterAntike.exe   — programa
echo     instalar.bat        — instalador (doble clic)
echo     instalar.ps1        — script del instalador
echo  ===================================================
echo.
pause
