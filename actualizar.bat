@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Plotter Antike — Actualizar y Publicar

echo.
echo  ===================================================
echo   Plotter Antike ^| Compilar, Instalar y Publicar
echo  ===================================================
echo.

echo  [1/7] Limpiando cache anterior...
if exist build\PlotterAntike rmdir /s /q build\PlotterAntike
if exist build\PlotterSTM   rmdir /s /q build\PlotterSTM
if exist dist\PlotterAntike.exe del /f /q dist\PlotterAntike.exe
if exist dist\PlotterAntike-installer.zip del /f /q dist\PlotterAntike-installer.zip
echo        OK
echo.

echo  [2/7] Instalando herramientas de build...
pip install pyinstaller pillow --quiet --upgrade
if errorlevel 1 ( echo  ERROR: pip install fallo. & pause & exit /b 1 )
echo        OK
echo.

echo  [3/7] Generando icono...
python crear_icono.py
if errorlevel 1 ( echo  ERROR: No se pudo generar icon.ico. & pause & exit /b 1 )
echo.

echo  [4/7] Compilando ejecutable...
python -m PyInstaller PlotterAntike.spec --noconfirm --clean
if errorlevel 1 ( echo  ERROR: PyInstaller fallo. & pause & exit /b 1 )
echo.

echo  [5/7] Instalando localmente...
copy /Y instalar.bat "dist\instalar.bat" >nul
copy /Y instalar.ps1 "dist\instalar.ps1" >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dist\instalar.ps1"
if errorlevel 1 (
    echo  ERROR: La instalacion fallo.
    pause
    exit /b 1
)
echo.

echo  [6/7] Creando paquete de descarga...
echo. > dist\INSTRUCCIONES.txt
echo  Plotter Antike — Instalacion >> dist\INSTRUCCIONES.txt
echo  ============================= >> dist\INSTRUCCIONES.txt
echo. >> dist\INSTRUCCIONES.txt
echo  1. Extrae todos los archivos de este zip a una carpeta. >> dist\INSTRUCCIONES.txt
echo  2. Haz doble clic en "instalar.bat". >> dist\INSTRUCCIONES.txt
echo  3. Espera a que termine. Se creara un acceso directo en el Escritorio. >> dist\INSTRUCCIONES.txt
echo  4. Abre la app desde el acceso directo del Escritorio. >> dist\INSTRUCCIONES.txt
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\PlotterAntike.exe','dist\instalar.bat','dist\instalar.ps1','dist\INSTRUCCIONES.txt' -DestinationPath 'dist\PlotterAntike-installer.zip'"
if errorlevel 1 ( echo  ERROR: No se pudo crear el zip. & pause & exit /b 1 )
echo        OK
echo.

echo  [7/7] Publicando release en GitHub...
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy.MM.dd"') do set TAG=v%%i
gh release delete "%TAG%" --yes >nul 2>&1
gh release create "%TAG%" "dist\PlotterAntike-installer.zip#PlotterAntike-installer.zip" --title "Plotter Antike %TAG%" --notes "## Instalacion%0a%0a1. Descarga **PlotterAntike-installer.zip**%0a2. Extrae la carpeta%0a3. Doble clic en **instalar.bat**%0a4. Se crea un acceso directo en el Escritorio" --latest
if errorlevel 1 ( echo  ERROR: No se pudo publicar en GitHub. & pause & exit /b 1 )
echo        OK
echo.

echo  ===================================================
echo   Listo!
echo.
echo   Instalado localmente y publicado en GitHub.
echo   Link de descarga:
echo   https://github.com/pepegarfe/plotter-antike/releases/latest
echo  ===================================================
echo.
pause
