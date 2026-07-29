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
# Convencion Fabricante\Aplicacion (como Google\Chrome). Renombrado 29-jul-2026: antes el
# fabricante era 'Antike'. La instalacion vieja se borra mas abajo, tras copiar la nueva.
$vendor      = 'BuiltByJose'
$vendorViejo = 'Antike'
$dest    = Join-Path $env:LOCALAPPDATA "$vendor\$folder"
$destExe = Join-Path $dest $exeName
$destViejo = Join-Path $env:LOCALAPPDATA "$vendorViejo\$folder"

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

# Quitar la "marca de internet" (flujo alterno Zone.Identifier) que Windows le pega a
# TODO lo que sale de un .zip bajado del navegador.
# OJO: sin esto la app NO ARRANCA. pywebview necesita pythonnet, y .NET se NIEGA a cargar
# un ensamblado marcado como de zona Internet. El sintoma es un cuadro de error con
# "Failed to resolve Python.Runtime.Loader.Initialize": el DLL esta ahi, pero bloqueado.
# (Este archivo se mantiene 100% ASCII a proposito: PowerShell 5.1 lee UTF-8 sin BOM
#  como ANSI y destroza los acentos.)
Write-Host ' Desbloqueando archivos (marca de internet)...'
Get-ChildItem -Path $dest -Recurse -File -Force -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue
Write-Host '   OK' -ForegroundColor Green

# Quitar la instalacion vieja (fabricante 'Antike'), ya que la nueva quedo copiada bien.
# GUARDAS a proposito: solo borra si la ruta es EXACTAMENTE la vieja esperada, si no es la
# misma que acabamos de instalar, y si de verdad contiene el .exe de esta app. Nunca se le
# pasa al comando una ruta que no haya pasado esas tres pruebas.
if ((Test-Path $destViejo) -and ($destViejo -ne $dest) -and
    (Test-Path (Join-Path $destViejo $exeName))) {
    Write-Host " Quitando la instalacion anterior: $destViejo"
    Remove-Item -Path $destViejo -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $destViejo) {
        Write-Host "   No se pudo borrar del todo. Puedes borrarla a mano." -ForegroundColor Yellow
    } else {
        Write-Host '   OK' -ForegroundColor Green
        # Si la carpeta del fabricante viejo quedo vacia, se va tambien.
        $vendorDirViejo = Join-Path $env:LOCALAPPDATA $vendorViejo
        if ((Test-Path $vendorDirViejo) -and
            (-not (Get-ChildItem $vendorDirViejo -Force -ErrorAction SilentlyContinue))) {
            Remove-Item $vendorDirViejo -Force -ErrorAction SilentlyContinue
        }
    }
}

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

$startDir = Join-Path ([Environment]::GetFolderPath('Programs')) $vendor
if (-not (Test-Path $startDir)) { New-Item -ItemType Directory -Path $startDir -Force | Out-Null }
New-Shortcut (Join-Path $startDir "$appName.lnk") $destExe $dest $desc
# El acceso directo viejo del menu de inicio apuntaba a una carpeta que ya no existe.
$startViejo = Join-Path ([Environment]::GetFolderPath('Programs')) $vendorViejo
if (Test-Path (Join-Path $startViejo "$appName.lnk")) {
    Remove-Item (Join-Path $startViejo "$appName.lnk") -Force -ErrorAction SilentlyContinue
    if (-not (Get-ChildItem $startViejo -Force -ErrorAction SilentlyContinue)) {
        Remove-Item $startViejo -Force -ErrorAction SilentlyContinue
    }
}
Write-Host " Acceso directo en el Menu Inicio" -ForegroundColor Green

Write-Host ''
Write-Host ' ===================================================' -ForegroundColor Green
Write-Host '  Listo. Abre "Design Studio" desde el Escritorio.' -ForegroundColor Green
Write-Host ' ===================================================' -ForegroundColor Green
Write-Host ''
Read-Host ' Presiona Enter para cerrar'
