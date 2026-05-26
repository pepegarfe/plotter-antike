#Requires -Version 3.0
# Desinstalador de Plotter Antike
$ErrorActionPreference = 'Stop'

$appName = 'Plotter Antike'
$dest    = Join-Path $env:LOCALAPPDATA 'Antike\PlotterController'
$destExe = Join-Path $dest 'PlotterAntike.exe'

Write-Host ''
Write-Host ' ===================================================' -ForegroundColor Cyan
Write-Host "  Desinstalando $appName" -ForegroundColor Cyan
Write-Host ' ===================================================' -ForegroundColor Cyan
Write-Host ''

# Cerrar la app si esta corriendo
$running = Get-Process -Name 'PlotterAntike' -ErrorAction SilentlyContinue
if ($running) {
    Write-Host " Cerrando $appName..." -ForegroundColor Yellow
    $running | Stop-Process -Force
    Start-Sleep -Milliseconds 800
    Write-Host '   OK' -ForegroundColor Green
    Write-Host ''
}

# Eliminar carpeta de instalacion
if (Test-Path $dest) {
    Write-Host " Eliminando archivos en: $dest"
    Remove-Item $dest -Recurse -Force
    Write-Host '   OK' -ForegroundColor Green
} else {
    Write-Host " La carpeta de instalacion no existe: $dest" -ForegroundColor Yellow
}

# Eliminar carpeta Antike si quedo vacia
$antikeDir = Join-Path $env:LOCALAPPDATA 'Antike'
if ((Test-Path $antikeDir) -and (-not (Get-ChildItem $antikeDir -ErrorAction SilentlyContinue))) {
    Remove-Item $antikeDir -Force
}

# Eliminar acceso directo del Escritorio
$desktop    = [Environment]::GetFolderPath('Desktop')
$lnkDesktop = Join-Path $desktop "$appName.lnk"
if (Test-Path $lnkDesktop) {
    Remove-Item $lnkDesktop -Force
    Write-Host " Acceso directo del Escritorio eliminado" -ForegroundColor Green
}

# Eliminar acceso directo del Menu de Inicio
$startDir = Join-Path ([Environment]::GetFolderPath('Programs')) 'Antike'
$lnkStart = Join-Path $startDir "$appName.lnk"
if (Test-Path $lnkStart) {
    Remove-Item $lnkStart -Force
    Write-Host " Acceso directo del Menu Inicio eliminado" -ForegroundColor Green
}
if ((Test-Path $startDir) -and (-not (Get-ChildItem $startDir -ErrorAction SilentlyContinue))) {
    Remove-Item $startDir -Force
}

Write-Host ''
Write-Host ' ===================================================' -ForegroundColor Green
Write-Host '  Desinstalacion completada!' -ForegroundColor Green
Write-Host ' ===================================================' -ForegroundColor Green
Write-Host ''
Read-Host ' Presiona Enter para cerrar'
