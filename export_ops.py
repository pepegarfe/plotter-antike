#!/usr/bin/env python3
"""
Exportar el diseño a formatos de intercambio: PNG, JPG, PDF, SVG y DXF.

Es el "Exportar como…" de Illustrator. NO sustituye al archivo de máquina (HPGL /
G-code), que sigue por su propio camino: esto es para mandar una muestra al cliente,
imprimir, o pasarle el vector a otro programa.

Convenciones (importantes, no obvias):
- **Entra todo en milímetros y con la Y hacia ARRIBA**, que es como vive la geometría en
  la interfaz. PDF, SVG y los mapas de píxeles usan la Y hacia ABAJO, así que aquí se
  voltea UNA vez, al final. DXF es Y-arriba de nacimiento y no se toca.
- **Unidades de dibujo**: la UI manda `units` = listas de índices de `paths`. Cada unidad
  se rellena con **regla par-impar** (un anillo dentro de otro abre hueco), la misma
  convención del motor de corte — así lo exportado coincide con lo que se ve y con lo
  que quedará de material.
- Sin dependencias nuevas: PDF y rasterizado con **pymupdf** (que ya se usa para leer
  .ai) y DXF con **ezdxf** (que ya se usa para leerlos). PNG/JPG se obtienen
  rasterizando el MISMO PDF, así el vector y la imagen nunca se contradicen.
"""
import io
import math

FORMATS = ('png', 'jpg', 'pdf', 'svg', 'dxf')
_MM_PT = 72.0 / 25.4          # milímetros → puntos PostScript
_CLOSED_TOL = 0.05            # mm; MISMO criterio que la interfaz y los motores
_LINE_MM = 0.25               # grosor de línea del contorno exportado
_MAX_PX = 60_000_000          # techo de píxeles: evita quedarse sin memoria con DPI absurdo

try:
    import fitz                                   # pymupdf
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    import ezdxf
    HAS_DXF = True
except ImportError:
    HAS_DXF = False


def is_closed(pts):
    return len(pts) > 2 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) <= _CLOSED_TOL


def _clean(paths):
    out = []
    for p in paths or []:
        pts = [(float(q[0]), float(q[1])) for q in (p or []) if len(q) >= 2]
        out.append(pts if len(pts) >= 2 else [])
    return out


def _bbox(paths):
    xs = [x for p in paths for x, _ in p]
    ys = [y for p in paths for _, y in p]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _frame(paths, opts):
    """Qué trozo de mundo entra en la página, en mm: (x0, y0, ancho, alto)."""
    if opts.get('area') == 'sheet':
        w, h = opts.get('work') or [3000.0, 600.0]
        return 0.0, 0.0, max(1.0, float(w)), max(1.0, float(h))
    b = _bbox(paths)
    if not b:
        return 0.0, 0.0, 100.0, 100.0
    m = max(0.0, float(opts.get('margin', 5.0)))
    w, h = b[2] - b[0], b[3] - b[1]
    # Un diseño de una sola línea recta tiene lado cero: se le da cuerpo o la página
    # saldría degenerada (y el rasterizado, de 0 píxeles).
    if w < 0.01: w = 0.01
    if h < 0.01: h = 0.01
    return b[0] - m, b[1] - m, w + 2 * m, h + 2 * m


def _units_of(paths, opts):
    """[(anillos_cerrados, trazos_abiertos)] por unidad de dibujo."""
    idxs = opts.get('units')
    if not idxs:
        idxs = [[i] for i in range(len(paths))]
    out = []
    for u in idxs:
        cerrados, abiertos = [], []
        for i in u:
            if not (0 <= i < len(paths)) or not paths[i]:
                continue
            (cerrados if is_closed(paths[i]) else abiertos).append(paths[i])
        if cerrados or abiertos:
            out.append((cerrados, abiertos))
    return out


# ── PDF (y, a partir de él, PNG/JPG) ──────────────────────────────────────────

def _pdf_doc(paths, opts):
    if not HAS_PDF:
        raise RuntimeError('Falta pymupdf: no se puede exportar a PDF/PNG/JPG.')
    x0, y0, wmm, hmm = _frame(paths, opts)
    doc = fitz.open()
    page = doc.new_page(width=wmm * _MM_PT, height=hmm * _MM_PT)

    def P(pt):
        """mm con Y arriba → puntos con Y abajo (el volteo vive AQUÍ y solo aquí)."""
        return fitz.Point((pt[0] - x0) * _MM_PT, (hmm - (pt[1] - y0)) * _MM_PT)

    negro = (0, 0, 0)
    ancho = _LINE_MM * _MM_PT
    rellenar = bool(opts.get('fill'))
    for cerrados, abiertos in _units_of(paths, opts):
        if cerrados:
            sh = page.new_shape()
            for r in cerrados:
                sh.draw_polyline([P(q) for q in r])
            # even_odd: el hueco de la "O" queda hueco, como en el lienzo y en el corte
            sh.finish(color=negro, fill=negro if rellenar else None,
                      even_odd=True, width=ancho, closePath=True)
            sh.commit()
        for a in abiertos:                       # los abiertos nunca se rellenan
            sh = page.new_shape()
            sh.draw_polyline([P(q) for q in a])
            sh.finish(color=negro, fill=None, width=ancho, closePath=False)
            sh.commit()
    return doc, wmm, hmm


def _pdf(paths, opts):
    doc, _, _ = _pdf_doc(paths, opts)
    return doc.tobytes()


def _raster(paths, opts, fmt):
    doc, wmm, hmm = _pdf_doc(paths, opts)
    dpi = int(opts.get('dpi') or 300)
    dpi = max(36, min(1200, dpi))
    px = (wmm / 25.4 * dpi) * (hmm / 25.4 * dpi)
    if px > _MAX_PX:                              # baja el DPI en vez de tronar
        dpi = max(36, int(dpi * math.sqrt(_MAX_PX / px)))
    # JPG no tiene transparencia: siempre fondo blanco.
    alpha = bool(opts.get('transparent', True)) and fmt == 'png'
    pix = doc[0].get_pixmap(dpi=dpi, alpha=alpha)
    return pix.tobytes('png' if fmt == 'png' else 'jpg')


# ── SVG ───────────────────────────────────────────────────────────────────────

def _svg(paths, opts):
    x0, y0, wmm, hmm = _frame(paths, opts)
    n = lambda v: ('%.4f' % v).rstrip('0').rstrip('.')          # noqa: E731
    def d_of(rings, cerrar):
        d = []
        for r in rings:
            d.append('M' + n((r[0][0] - x0)) + ',' + n(hmm - (r[0][1] - y0)))
            for q in r[1:]:
                d.append('L' + n(q[0] - x0) + ',' + n(hmm - (q[1] - y0)))
            if cerrar:
                d.append('Z')
        return ' '.join(d)

    rellenar = bool(opts.get('fill'))
    cuerpo = []
    for cerrados, abiertos in _units_of(paths, opts):
        if cerrados:
            cuerpo.append('<path d="%s" fill="%s" fill-rule="evenodd" stroke="#000" '
                          'stroke-width="%s"/>' %
                          (d_of(cerrados, True), '#000' if rellenar else 'none', n(_LINE_MM)))
        for a in abiertos:
            cuerpo.append('<path d="%s" fill="none" stroke="#000" stroke-width="%s"/>' %
                          (d_of([a], False), n(_LINE_MM)))
    svg = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
           'width="%smm" height="%smm" viewBox="0 0 %s %s">\n'
           '<g stroke-linejoin="round" stroke-linecap="round">\n%s\n</g>\n</svg>\n'
           % (n(wmm), n(hmm), n(wmm), n(hmm), '\n'.join(cuerpo)))
    return svg.encode('utf-8')


# ── DXF ───────────────────────────────────────────────────────────────────────

def _dxf(paths, opts):
    if not HAS_DXF:
        raise RuntimeError('Falta ezdxf: no se puede exportar a DXF.')
    x0, y0, _, _ = _frame(paths, opts)
    doc = ezdxf.new('R2010')
    doc.header['$INSUNITS'] = 4                   # 4 = milímetros; sin esto el receptor adivina
    msp = doc.modelspace()
    for p in paths:
        if not p:
            continue
        cerrado = is_closed(p)
        # En un LWPOLYLINE cerrado el último punto SOBRA: repetirlo deja un segmento
        # de largo cero que algunos CAM leen como un pinchazo.
        pts = p[:-1] if cerrado else p
        msp.add_lwpolyline([(q[0] - x0, q[1] - y0) for q in pts], close=cerrado)
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode('utf-8')


# ── entrada única ─────────────────────────────────────────────────────────────

_WRITERS = {
    'pdf': lambda p, o: _pdf(p, o),
    'svg': lambda p, o: _svg(p, o),
    'dxf': lambda p, o: _dxf(p, o),
    'png': lambda p, o: _raster(p, o, 'png'),
    'jpg': lambda p, o: _raster(p, o, 'jpg'),
}


def export_bytes(fmt, data):
    """Devuelve {'ok':True,'bytes':b'…','ext':'png'} o {'ok':False,'error':…}."""
    fmt = str(fmt or '').lower().lstrip('.')
    if fmt in ('jpeg',):
        fmt = 'jpg'
    if fmt not in _WRITERS:
        return {'ok': False, 'error': f'Formato desconocido: {fmt}. Usa {", ".join(FORMATS)}.'}
    data = data or {}
    paths = _clean(data.get('paths'))
    if not any(paths):
        return {'ok': False, 'error': 'No hay nada que exportar.'}
    try:
        return {'ok': True, 'bytes': _WRITERS[fmt](paths, data), 'ext': fmt}
    except Exception as e:
        return {'ok': False, 'error': f'No se pudo exportar a {fmt.upper()}: {e}'}
