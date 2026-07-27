#!/usr/bin/env python3
"""
Deja potrace listo para viajar DENTRO de la app compilada, en `vendor/`.

Por qué: el calco de imagen en blanco y negro llama a `potrace`, que es un programa
aparte. En esta Mac existe porque está Homebrew; el taller que instale Design Studio
no lo tiene. Sin esta copia, el calco B/N truena en la app distribuida.

  Mac      → copia potrace + su librería (libpotrace.0.dylib) y REESCRIBE la ruta de
             la librería a `@loader_path`, para que la busque a su lado y no en
             /opt/homebrew (que no existe en la máquina del usuario).
  Windows  → baja el potrace oficial (un .exe suelto, sin DLLs) y lo deja en vendor/.

potrace es software libre (GPL) de Peter Selinger — se distribuye SIN modificar, como
programa aparte que la app invoca. Fuente: https://potrace.sourceforge.net/
"""
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE / 'vendor'
WIN_URL = 'https://potrace.sourceforge.net/download/1.16/potrace-1.16.win64.zip'


def _mac():
    src = shutil.which('potrace') or '/opt/homebrew/bin/potrace'
    if not os.path.exists(src):
        raise SystemExit('No hay potrace instalado. Instálalo con: brew install potrace')
    VENDOR.mkdir(exist_ok=True)
    dst = VENDOR / 'potrace'
    shutil.copy2(src, dst)
    dst.chmod(0o755)

    # ¿De qué librerías propias depende? (las de /usr/lib son del sistema y sí existen
    # en cualquier Mac; las de Homebrew hay que llevárselas)
    out = subprocess.run(['otool', '-L', str(dst)], capture_output=True, text=True).stdout
    for line in out.splitlines()[1:]:
        m = re.match(r'\s+(\S+)', line)
        if not m:
            continue
        lib = m.group(1)
        if lib.startswith('/usr/lib/') or lib.startswith('/System/'):
            continue
        name = os.path.basename(lib)
        real = lib
        if not os.path.exists(real):
            raise SystemExit(f'No se encontró la librería {lib}')
        shutil.copy2(real, VENDOR / name)
        (VENDOR / name).chmod(0o755)
        # @loader_path = "junto al binario que la carga"
        subprocess.run(['install_name_tool', '-change', lib, f'@loader_path/{name}', str(dst)],
                       check=True)
        subprocess.run(['install_name_tool', '-id', f'@loader_path/{name}', str(VENDOR / name)],
                       check=True)
        print(f'    libreria incluida: {name}')

    # Re-firmar: cambiar el binario invalida su firma ad-hoc y macOS lo mata al abrirlo.
    subprocess.run(['codesign', '--force', '-s', '-', str(dst)], check=True,
                   capture_output=True)
    for f in VENDOR.glob('*.dylib'):
        subprocess.run(['codesign', '--force', '-s', '-', str(f)], check=True,
                       capture_output=True)
    return dst


def _win():
    VENDOR.mkdir(exist_ok=True)
    dst = VENDOR / 'potrace.exe'
    zpath = VENDOR / 'potrace-win.zip'
    print(f'    bajando {WIN_URL}')
    urllib.request.urlretrieve(WIN_URL, zpath)
    with zipfile.ZipFile(zpath) as z:
        member = next(n for n in z.namelist() if n.lower().endswith('/potrace.exe')
                      or n.lower() == 'potrace.exe')
        with z.open(member) as f, open(dst, 'wb') as o:
            shutil.copyfileobj(f, o)
    zpath.unlink()
    return dst


def main():
    dst = _mac() if sys.platform == 'darwin' else _win()
    # Comprobar que el potrace preparado ARRANCA de verdad (no basta con copiarlo).
    r = subprocess.run([str(dst), '--version'], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f'El potrace preparado no corre: {r.stderr.strip()}')
    print(f'OK  {dst}  ->  {r.stdout.splitlines()[0].strip()}')


if __name__ == '__main__':
    main()
