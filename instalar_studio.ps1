#Requires -Version 3.0
# Instalador de Design Studio (Windows).
# Copia la CARPETA de la aplicacion a AppData del usuario (sin pedir permisos de
# administrador) y crea accesos directos. La misma carpeta es la que reemplaza la
# auto-actualizacion, asi que no hay dos copias que se contradigan.
$ErrorActionPreference = 'Stop'

$appName = 'Design Studio'
$folder  = 'DesignStudio'
$exeName = 'DesignStudio.exe'
$src     = Join-Path $PSScriptRoot $folder
$dest    = Join-Path $env:LOCALAPPDATA "Antike\$folder"
$destExe = Join-Path $dest $exeName

Write-Host ''
Write-Host ' ===================================================' -ForegroundColor Magenta
Write-Host "  Instalando $appName" -ForegroundColor Magenta
Write-Host ' ===================================================' -ForegroundColor Magenta
Write-Host ''

if (-not (Test-Path (Join-Path $src $exeName))) {
    Write-Host " ERROR: No se encontro la carpeta $folder junto a este instalador." -ForegroundColor Red
    Write-Host "        Extrae TODO el zip antes de ejecutar (no lo corras desde dentro del zip)."
    Write-Host ''
    Read-Host ' Presiona Enter para cerrar'
    exit 1
}

# Cerrar la app si esta corriendo (si no, el .exe queda bloqueado y no se puede copiar)
$running = Get-Process -Name 'DesignStudio' -ErrorAction SilentlyContinue
if ($running) {
    Write-Host " Cerrando la instancia anterior..." -ForegroundColor Yellow
    $running | Stop-Process -Force
    Start-Sleep -Milliseconds 900
}

Write-Host " Instalando en: $dest"
if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }
# /MIR deja la carpeta IDENTICA a la nueva: sin restos de versiones anteriores.
robocopy $src $dest /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) {
    Write-Host " ERROR: No se pudieron copiar los archivos (codigo $LASTEXITCODE)." -ForegroundColor Red
    Read-Host ' Presiona Enter para cerrar'
    exit 1
}
Write-Host '   OK' -ForegroundColor Green

function New-Shortcut {
    param($LnkPath, $Target, $WorkDir, $Desc)
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($LnkPath)
    $sc.TargetPath       = $Target
    $sc.WorkingDirectory = $WorkDir
    $sc.Description      = $Desc
    $sc.Save()
}

$desc       = 'Design Studio - diseno, plotter de corte y CNC'
$desktop    = [Environment]::GetFolderPath('Desktop')
New-Shortcut (Join-Path $desktop "$appName.lnk") $destExe $dest $desc
Write-Host " Acceso directo en el Escritorio" -ForegroundColor Green

$startDir = Join-Path ([Environment]::GetFolderPath('Programs')) 'Antike'
if (-not (Test-Path $startDir)) { New-Item -ItemType Directory -Path $startDir -Force | Out-Null }
New-Shortcut (Join-Path $startDir "$appName.lnk") $destExe $dest $desc
Write-Host " Acceso directo en el Menu Inicio" -ForegroundColor Green

Write-Host ''
Write-Host ' ===================================================' -ForegroundColor Green
Write-Host '  Listo. Abre "Design Studio" desde el Escritorio.' -ForegroundColor Green
Write-Host ' ===================================================' -ForegroundColor Green
Write-Host ''
Read-Host ' Presiona Enter para cerrar'
