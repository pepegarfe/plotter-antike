# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec para Plotter Antike

a = Analysis(
    ['plotter_control.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('icon.ico', '.'),   # icono disponible en sys._MEIPASS para la ventana
    ],
    hiddenimports=[
        'serial',
        'serial.tools',
        'serial.tools.list_ports',
        'svgpathtools',
        'ezdxf',
        'fitz',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PlotterAntike',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # sin ventana de consola
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)
