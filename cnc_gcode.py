#!/usr/bin/env python3
"""
Trayectorias de corte y G-code (.tap) para la CNC RichAuto — Fase B de Design Studio.

Recibe los trazados EFECTIVOS del diseño (mm, Y hacia arriba — la misma geometría que se ve
en el lienzo) y produce:
- make_toolpaths(): las polilíneas que recorrerá el CENTRO de la fresa, compensadas con
  shapely según el lado de corte (fuera/dentro/sobre la línea) y conscientes del anidado
  (una letra "O": el contorno de afuera se expande y el hueco se contrae, como en Aspire).
- build_gcode(): el archivo G-code en el dialecto más conservador que existe — solo
  G00/G01, sin arcos — que es exactamente lo que el manual de RichAuto usa en sus ejemplos
  y evita los problemas de G02/G03 reportados con estos controladores DSP.

Convenciones (ver .claude/memoria/cnc-richauto.md):
- Unidades mm (G21), coordenadas absolutas (G90). Avances en mm/min.
- ⚠️ El controlador puede IGNORAR F y S de fábrica ("F Read = Ign" en el handle:
  AUTO PRO SETUP → G Code Setup). El archivo los incluye siempre; si la máquina no
  los respeta, es ese ajuste — no un bug del archivo.
- Cero de Z: 'top' = cara superior del material (Z negativa corta), 'bed' = cama
  (la cara superior queda en Z = grosor).
"""
import math

try:
    from shapely.geometry import Polygon
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

_CLOSE_TOL = 0.05   # mm: un trazado cuyo fin coincide con su inicio (±tolerancia) es cerrado
_SAFE_MM = 5.0      # altura de seguridad sobre la cara superior del material


def _is_closed(pts):
    return (len(pts) >= 4 and
            math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) <= _CLOSE_TOL)


def _rings(geom):
    """Todos los anillos (exteriores e interiores) de un Polygon/MultiPolygon, como listas de puntos."""
    polys = getattr(geom, 'geoms', [geom])
    out = []
    for p in polys:
        if p.is_empty or not isinstance(p, Polygon):
            continue
        out.append([list(c) for c in p.exterior.coords])
        for hole in p.interiors:
            out.append([list(c) for c in hole.coords])
    return out


def make_toolpaths(paths, side, tool_dia):
    """Polilíneas del centro de la fresa.

    paths: [[(x,y),...], ...] en mm (geometría efectiva del diseño).
    side:  'outside' | 'inside' | 'on'.
    Devuelve (toolpaths, n_abiertos_saltados).
    """
    if side == 'on':
        return [[list(p) for p in pts] for pts in paths if len(pts) >= 2], 0
    if not HAS_SHAPELY:
        raise RuntimeError('Falta shapely para compensar la fresa. '
                           'Instálala con: pip install shapely')
    closed, skipped = [], 0
    for pts in paths:
        if _is_closed(pts):
            poly = Polygon(pts)
            if not poly.is_valid:
                poly = poly.buffer(0)   # repara auto-intersecciones
            if not poly.is_empty:
                closed.append(poly)
        elif len(pts) >= 2:
            skipped += 1   # un trazo abierto no tiene "fuera"/"dentro"
    if not closed:
        return [], skipped
    # Anidado par-impar (como se pintan los rellenos): contorno dentro de contorno = hueco.
    region = None
    for p in closed:
        region = p if region is None else region.symmetric_difference(p)
    r = float(tool_dia) / 2.0
    offset = region.buffer(r if side == 'outside' else -r, quad_segs=16)
    return _rings(offset), skipped


def _passes(depth, pass_depth):
    n = max(1, math.ceil(depth / max(0.1, pass_depth)))
    return [min(depth, pass_depth * (i + 1)) for i in range(n)]


def _f(v):
    s = ('%.3f' % v).rstrip('0').rstrip('.')
    return s if s not in ('-0', '') else '0'


def _ascii(s):
    """Comentarios en ASCII puro: el manual de RichAuto advierte que caracteres no
    estándar en el archivo pueden hacer que el controlador falle al leerlo."""
    import unicodedata
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode('ascii')
    return ''.join(c if c.isprintable() and c not in '()' else ' ' for c in s).strip()


def build_gcode(toolpaths, tool, material, depth, name=''):
    """Arma el .tap completo. Devuelve (texto, segundos_estimados)."""
    thick = float(material.get('thickness', 15.0))
    z_top = thick if material.get('z_zero') == 'bed' else 0.0   # Z de la cara superior
    safe = z_top + _SAFE_MM
    feed, plunge = float(tool['feed']), float(tool['plunge'])
    depths = _passes(float(depth), float(tool['pass_depth']))
    lines = [
        '( %s - Design Studio )' % _ascii(name or 'diseno'),
        '( Fresa: %s / O %s mm / %d pasadas hasta %s mm )' %
        (_ascii(tool.get('name', '?')), _f(float(tool['dia'])), len(depths), _f(float(depth))),
        'G90 G21 G17',
        'G00 Z%s' % _f(safe),
        'M03 S%d' % int(float(tool.get('rpm', 18000))),
    ]
    secs = 0.0
    for pts in toolpaths:
        if len(pts) < 2:
            continue
        length = sum(math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
                     for i in range(1, len(pts)))
        lines.append('G00 X%s Y%s' % (_f(pts[0][0]), _f(pts[0][1])))
        for d in depths:
            lines.append('G01 Z%s F%s' % (_f(z_top - d), _f(plunge)))
            for p in pts[1:]:
                lines.append('G01 X%s Y%s F%s' % (_f(p[0]), _f(p[1]), _f(feed)))
            secs += (length / feed + d / plunge) * 60.0
            if not _is_closed(pts) and d != depths[-1]:
                # trazo abierto: volver al inicio por arriba antes de la siguiente pasada
                lines.append('G00 Z%s' % _f(safe))
                lines.append('G00 X%s Y%s' % (_f(pts[0][0]), _f(pts[0][1])))
        lines.append('G00 Z%s' % _f(safe))
    lines += ['M05', 'G00 X0 Y0', 'M30']
    return '\n'.join(lines) + '\n', secs
