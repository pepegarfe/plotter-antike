#!/usr/bin/env python3
"""
Genera el ícono de Design Studio para las dos plataformas.

  studio.ico   → Windows (PyInstaller lo incrusta en el .exe)
  studio.icns  → Mac (solo se puede generar EN Mac: usa `iconutil` del sistema)

El dibujo es la marca de la app: cuadro magenta con la cabeza de corte en blanco
(los dos círculos y las guías del logo de la barra superior).
"""
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw

ACCENT = '#E5006D'      # magenta de marca
ACCENT_DK = '#B00055'
WHITE = '#ffffff'

SIZES = [16, 24, 32, 48, 64, 128, 256, 512, 1024]


def draw_icon(size):
    """La marca: dos ruedas (los círculos) y las guías cruzadas del cabezal."""
    s = size * 4                                  # se dibuja en grande y se reduce (antialias)
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Plano a propósito: ImageDraw NO mezcla transparencias, las REEMPLAZA — un
    # "brillo" con alpha dibujado encima abre un hueco en vez de aclarar.
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=ACCENT)

    pad = 0.16                                     # aire alrededor de la marca
    def P(x, y):                                   # coordenadas del SVG (24×24) → píxeles
        k = s * (1 - 2 * pad) / 24.0
        return (s * pad + x * k, s * pad + y * k)

    lw = max(2, int(s * (1 - 2 * pad) * 2.0 / 24))
    r = s * (1 - 2 * pad) * 3.0 / 24
    for cx, cy in ((6, 6), (6, 18)):
        c = P(cx, cy)
        d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], outline=WHITE, width=lw)
    d.line([P(20, 4), P(8.12, 15.88)], fill=WHITE, width=lw, joint='curve')
    d.line([P(14.47, 14.48), P(20, 20)], fill=WHITE, width=lw, joint='curve')
    d.line([P(8.12, 8.12), P(12, 12)], fill=WHITE, width=lw, joint='curve')
    return img.resize((size, size), Image.LANCZOS)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    imgs = {n: draw_icon(n) for n in SIZES}

    ico = os.path.join(here, 'studio.ico')
    imgs[256].save(ico, format='ICO',
                   sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
    print(f'OK  {ico}')

    if sys.platform != 'darwin':
        print('    .icns se genera solo en Mac (necesita iconutil): se omite.')
        return
    iconset = os.path.join(here, 'studio.iconset')
    shutil.rmtree(iconset, ignore_errors=True)
    os.makedirs(iconset)
    # Nombres EXACTOS que exige iconutil (base y @2x).
    for n in (16, 32, 128, 256, 512):
        imgs[n].save(os.path.join(iconset, f'icon_{n}x{n}.png'))
        imgs[n * 2].save(os.path.join(iconset, f'icon_{n}x{n}@2x.png'))
    icns = os.path.join(here, 'studio.icns')
    subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', icns], check=True)
    shutil.rmtree(iconset, ignore_errors=True)
    print(f'OK  {icns}')


if __name__ == '__main__':
    main()
