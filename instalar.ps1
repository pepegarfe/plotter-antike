#Requires -Version 3.0
# Instalador de Plotter Antike
$ErrorActionPreference = 'Stop'

$appName = 'Plotter Antike'
$exeName = 'PlotterAntike.exe'
$srcExe  = Join-Path $PSScriptRoot $exeName
$dest    = Join-Path $env:LOCALAPPDATA 'Antike\PlotterController'
$destExe = Join-Path $dest $exeName

Write-Host ''
Write-Host ' ===================================================' -ForegroundColor Cyan
Write-Host "  Instalando $appName" -ForegroundColor Cyan
Write-Host ' ===================================================' -ForegroundColor Cyan
Write-Host ''

# Verificar que el exe esta junto al instalador
if (-not (Test-Path $srcExe)) {
    Write-Host " ERROR: No se encontro $exeName" -ForegroundColor Red
    Write-Host "        Asegurate de que $exeName esta en la misma carpeta que este instalador."
    Write-Host ''
    Read-Host ' Presiona Enter para cerrar'
    exit 1
}

# Instalar en AppData del usuario (no requiere permisos de administrador)
Write-Host " Instalando en: $dest"
if (-not (Test-Path $dest)) {
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
}
Copy-Item $srcExe $destExe -Force
Write-Host '   OK' -ForegroundColor Green
Write-Host ''

# Funcion para crear accesos directos
function New-Shortcut {
    param($LnkPath, $Target, $WorkDir, $Desc)
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($LnkPath)
    $sc.TargetPath       = $Target
    $sc.WorkingDirectory = $WorkDir
    $sc.Description      = $Desc
    $sc.Save()
}

$desc = 'Plotter Antike - Controlador de Plotter de Corte'

# Acceso directo en el Escritorio
$desktop    = [Environment]::GetFolderPath('Desktop')
$lnkDesktop = Join-Path $desktop "$appName.lnk"
New-Shortcut $lnkDesktop $destExe $dest $desc
Write-Host " Acceso directo en Escritorio:" -NoNewline
Write-Host "  $lnkDesktop" -ForegroundColor Green

# Acceso directo en el Menu de Inicio
$startDir = Join-Path ([Environment]::GetFolderPath('Programs')) 'Antike'
if (-not (Test-Path $startDir)) {
    New-Item -ItemType Directory -Path $startDir -Force | Out-Null
}
$lnkStart = Join-Path $startDir "$appName.lnk"
New-Shortcut $lnkStart $destExe $dest $desc
Write-Host " Acceso directo en Menu Inicio:" -NoNewline
Write-Host " $lnkStart" -ForegroundColor Green

Write-Host ''
Write-Host ' ===================================================' -ForegroundColor Green
Write-Host '  Instalacion completada!' -ForegroundColor Green
Write-Host "  El programa esta en: $destExe" -ForegroundColor White
Write-Host ' ===================================================' -ForegroundColor Green
Write-Host ''
Read-Host ' Presiona Enter para cerrar'
