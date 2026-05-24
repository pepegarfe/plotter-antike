#!/usr/bin/env python3
"""Genera icon.ico para Plotter Antike."""
try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Pillow no instalado. Ejecuta:  pip install pillow")
    raise

BG     = '#1a3662'  # azul marino
AXIS   = '#ffffff'  # blanco (ejes)
NEG    = '#2d4e8a'  # azul oscuro (semi-ejes negativos)
CUTTER = '#e03030'  # rojo (cabezal)
PATH   = '#f0a020'  # naranja (trayectoria)


def draw_icon(size):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    # Fondo con esquinas redondeadas
    radius = max(3, size // 5)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=BG)

    cx, cy = size // 2, size // 2
    mg  = max(3, size // 7)          # margen hasta punta del eje
    lw  = max(1, size // 22)         # grosor de línea
    aw  = max(2, size // 9)          # tamaño de punta de flecha
    r2  = max(2, size // 9)          # radio del cabezal

    if size >= 32:
        # Semi-ejes negativos (tenues)
        d.line([(cx, cy), (mg,        cy)], fill=NEG, width=lw)
        d.line([(cx, cy), (cx, size - mg)], fill=NEG, width=lw)

        # Eje X positivo → derecha
        d.line([(cx, cy), (size - mg, cy)], fill=AXIS, width=lw)
        d.polygon([
            (size - mg,      cy),
            (size - mg - aw, cy - aw // 2),
            (size - mg - aw, cy + aw // 2),
        ], fill=AXIS)

        # Eje Y positivo → arriba (Y canvas invertido)
        d.line([(cx, cy), (cx, mg)], fill=AXIS, width=lw)
        d.polygon([
            (cx,            mg),
            (cx - aw // 2,  mg + aw),
            (cx + aw // 2,  mg + aw),
        ], fill=AXIS)

        # Trayectoria de corte (línea naranja diagonal)
        if size >= 48:
            x0 = mg + aw
            y0 = size - mg - aw
            x1 = cx + aw
            y1 = cy - aw
            seg = 6
            for i in range(0, seg, 2):
                t0 = i / seg
                t1 = min(1.0, (i + 1.4) / seg)
                d.line([
                    (int(x0 + (x1 - x0) * t0), int(y0 + (y1 - y0) * t0)),
                    (int(x0 + (x1 - x0) * t1), int(y0 + (y1 - y0) * t1)),
                ], fill=PATH, width=lw)

    # Cabezal de corte (círculo rojo en el origen)
    outline = AXIS if size >= 32 else None
    d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2],
              fill=CUTTER, outline=outline,
              width=max(1, size // 28))

    return img


def main():
    sizes  = [16, 24, 32, 48, 64, 128, 256]
    images = [draw_icon(s) for s in sizes]
    images[0].save(
        'icon.ico',
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    print('icon.ico generado correctamente.')


if __name__ == '__main__':
    main()
