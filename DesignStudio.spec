# -*- mode: python ; coding: utf-8 -*-
"""
Empaquetado de Design Studio (PyInstaller) para Mac y Windows.

  python crear_icono_studio.py      # iconos (studio.ico / studio.icns)
  python preparar_potrace.py        # potrace autónomo en vendor/  (opcional)
  python -m PyInstaller DesignStudio.spec --noconfirm --clean

⚠️ Es un paquete de CARPETA (onedir), no de archivo único: con pywebview + shapely +
pymupdf, el modo "onefile" tendría que descomprimir ~200 MB en cada arranque.
"""
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

HERE = Path(os.path.abspath(SPECPATH))
IS_MAC = sys.platform == 'darwin'

datas = [('studio_ui.html', '.'), ('three.bundle.js', '.'), ('version.txt', '.')]
binaries = []
hiddenimports = ['serial', 'serial.tools', 'serial.tools.list_ports']

# Librerías con datos/binarios propios que PyInstaller no adivina solo.
for pkg in ('webview', 'shapely', 'fontTools', 'vtracer', 'fitz', 'PIL'):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as e:
        print(f'[spec] aviso: no se pudo recolectar {pkg}: {e}')

hiddenimports += collect_submodules('ezdxf')

# potrace (calco B/N): viaja dentro del paquete si `preparar_potrace.py` lo dejó listo.
vendor = HERE / 'vendor'
if vendor.is_dir():
    for f in sorted(vendor.iterdir()):
        if f.is_file() and f.name != '.DS_Store':
            binaries.append((str(f), '.'))
    print(f'[spec] potrace incluido desde {vendor}')
else:
    # Sin acentos a proposito: la consola de Windows (cp1252) truena al imprimirlos.
    print('[spec] AVISO: sin vendor/ - la app no llevara potrace y el calco B/N '
          'solo funcionara donde ya este instalado (corre preparar_potrace.py).')

try:
    VERSION = (HERE / 'version.txt').read_text().strip() or '0.0.0'
except Exception:
    VERSION = '0.0.0'
# CFBundleShortVersionString debe ser numérico (1-3 números); 'dev' no le gusta a macOS.
PLIST_VER = VERSION if VERSION[:1].isdigit() else '0.0.0'

a = Analysis(
    ['design_studio.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DesignStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX corrompe binarios firmados en Mac y dispara antivirus en Windows
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(HERE / ('studio.icns' if IS_MAC else 'studio.ico')),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='DesignStudio',
)
app = BUNDLE(
    coll,
    name='DesignStudio.app',
    icon=str(HERE / 'studio.icns'),
    bundle_identifier='com.antike.designstudio',
    version=PLIST_VER,
    info_plist={
        'CFBundleName': 'Design Studio',
        'CFBundleDisplayName': 'Design Studio',
        'CFBundleShortVersionString': PLIST_VER,
        'CFBundleVersion': PLIST_VER,
        'NSHighResolutionCapable': True,        # sin esto se ve borroso en pantallas Retina
        'LSMinimumSystemVersion': '10.15',
        'NSHumanReadableCopyright': 'Antike',
    },
)
