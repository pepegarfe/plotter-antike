#!/usr/bin/env python3
"""
Trayectorias de corte y G-code (.tap) para la CNC RichAuto — Fases B y C de Design Studio.

Recibe los trazados EFECTIVOS del diseño (mm, Y hacia arriba — la misma geometría que se ve
en el lienzo) y produce:
- make_toolpaths(): PERFIL — el centro de la fresa compensado con shapely según el lado
  (fuera/dentro/sobre la línea), consciente del anidado (una letra "O": el contorno de
  afuera se expande y el hueco se contrae, como en Aspire).
- make_pocket(): VACIADO — anillos concéntricos hacia adentro (paso = stepover de la fresa)
  hasta vaciar el interior; los huecos anidados se respetan. Orden: de adentro hacia afuera,
  la pared queda al final (acabado más limpio).
- drill_points(): TALADRO — el centro (del bbox) de cada contorno cerrado.
- build_gcode() / build_drill(): el archivo G-code en el dialecto más conservador que existe
  — solo G00/G01, sin arcos — que es lo que el manual de RichAuto usa en sus ejemplos y
  evita los problemas de G02/G03 reportados con estos controladores DSP. build_gcode admite
  PUENTES (tabs): en las pasadas finales la fresa sube y pasa por encima de los puentes para
  que la pieza no salga volando al soltarse.

Convenciones (ver .claude/memoria/cnc-richauto.md):
- Unidades mm (G21), coordenadas absolutas (G90). Avances en mm/min.
- ⚠️ El controlador puede IGNORAR F y S de fábrica ("F Read = Ign" en el handle:
  AUTO PRO SETUP → G Code Setup). El archivo los incluye siempre.
- Cero de Z: 'top' = cara superior del material, 'bed' = cama (la cara queda en Z=grosor).
- Comentarios SOLO en ASCII: el manual advierte que caracteres raros rompen la lectura.
"""
import math

try:
    from shapely.geometry import Polygon
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

_CLOSE_TOL = 0.05   # mm: un trazado cuyo fin coincide con su inicio (±tolerancia) es cerrado
_SAFE_MM = 5.0      # altura de seguridad sobre la cara superior del material
_PECK_CLEAR = 2.0   # mm sobre el material al que sube el taladro entre picotazos


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


def _closed_region(paths):
    """Región par-impar (como se pintan los rellenos) de los trazados cerrados.
    Devuelve (region | None, n_abiertos_saltados)."""
    if not HAS_SHAPELY:
        raise RuntimeError('Falta shapely para compensar la fresa. '
                           'Instálala con: pip install shapely')
    region, skipped = None, 0
    for pts in paths:
        if _is_closed(pts):
            poly = Polygon(pts)
            if not poly.is_valid:
                poly = poly.buffer(0)   # repara auto-intersecciones
            if not poly.is_empty:
                region = poly if region is None else region.symmetric_difference(poly)
        elif len(pts) >= 2:
            skipped += 1
    return region, skipped


def make_toolpaths(paths, side, tool_dia):
    """PERFIL: polilíneas del centro de la fresa. side: 'outside' | 'inside' | 'on'."""
    if side == 'on':
        return [[list(p) for p in pts] for pts in paths if len(pts) >= 2], 0
    region, skipped = _closed_region(paths)
    if region is None:
        return [], skipped
    r = float(tool_dia) / 2.0
    offset = region.buffer(r if side == 'outside' else -r, quad_segs=16)
    return _rings(offset), skipped


def make_pocket(paths, tool_dia, stepover_mm):
    """VACIADO: anillos concéntricos hacia adentro. Por cada zona conexa, de adentro
    hacia afuera (la pared perimetral se corta al final)."""
    region, skipped = _closed_region(paths)
    if region is None:
        return [], skipped
    r = float(tool_dia) / 2.0
    step = max(0.5, float(stepover_mm))
    out = []
    for poly in getattr(region, 'geoms', [region]):
        levels = []
        k = 0
        while True:
            off = poly.buffer(-(r + k * step), quad_segs=16)
            if off.is_empty:
                break
            levels.append(_rings(off))
            k += 1
        for lev in reversed(levels):        # del centro hacia la pared
            out.extend(lev)
    return out, skipped


def drill_points(paths):
    """TALADRO: centro (del bbox) de cada contorno cerrado."""
    pts, skipped = [], 0
    for p in paths:
        if _is_closed(p):
            xs = [q[0] for q in p]
            ys = [q[1] for q in p]
            pts.append([(min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0])
        elif len(p) >= 2:
            skipped += 1
    return pts, skipped


# ---------- puentes (tabs) ----------

def _cum(pts):
    c = [0.0]
    for i in range(1, len(pts)):
        c.append(c[-1] + math.hypot(pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1]))
    return c


def _point_at(pts, cum, s):
    """Punto sobre la polilínea a distancia de arco s (interpolado)."""
    for i in range(1, len(pts)):
        if cum[i] >= s - 1e-9:
            seg = cum[i] - cum[i-1]
            t = 0.0 if seg <= 1e-12 else (s - cum[i-1]) / seg
            return [pts[i-1][0] + (pts[i][0] - pts[i-1][0]) * t,
                    pts[i-1][1] + (pts[i][1] - pts[i-1][1]) * t]
    return [pts[-1][0], pts[-1][1]]


def _sub(pts, cum, a, b):
    """Tramo de la polilínea entre distancias de arco a..b, con extremos interpolados."""
    out = [_point_at(pts, cum, a)]
    for i in range(len(pts)):
        if a + 1e-9 < cum[i] < b - 1e-9:
            out.append([pts[i][0], pts[i][1]])
    out.append(_point_at(pts, cum, b))
    return out


def _split_ring(pts, ntabs, tab_w):
    """Divide un anillo cerrado en tramos [(puntos, es_puente)] con ntabs puentes de
    ancho tab_w repartidos parejo (centrados lejos del punto de arranque)."""
    cum = _cum(pts)
    perim = cum[-1]
    if ntabs < 1 or tab_w <= 0 or perim <= ntabs * tab_w * 2:
        return None
    ivs = []
    for i in range(ntabs):
        c = perim * (i + 0.5) / ntabs
        a, b = c - tab_w / 2.0, c + tab_w / 2.0
        if a < 0:
            ivs += [(0.0, b), (perim + a, perim)]
        elif b > perim:
            ivs += [(a, perim), (0.0, b - perim)]
        else:
            ivs.append((a, b))
    cuts = sorted({0.0, perim} | {x for iv in ivs for x in iv})
    pieces = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        if b - a < 1e-6:
            continue
        mid = (a + b) / 2.0
        tab = any(x0 - 1e-9 <= mid <= x1 + 1e-9 for x0, x1 in ivs)
        pieces.append((_sub(pts, cum, a, b), tab))
    return pieces


# ---------- G-code ----------

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


def _header(name, tool, extra, depth, npasses):
    return [
        '( %s - Design Studio )' % _ascii(name or 'diseno'),
        '( Fresa: %s / O %s mm / %s / %d pasadas hasta %s mm )' %
        (_ascii(tool.get('name', '?')), _f(float(tool['dia'])), _ascii(extra),
         npasses, _f(float(depth))),
        'G90 G21 G17',
    ]


def _z_levels(material):
    thick = float(material.get('thickness', 15.0))
    z_top = thick if material.get('z_zero') == 'bed' else 0.0
    return z_top, z_top + _SAFE_MM


def build_gcode(toolpaths, tool, material, depth, name='', tabs=None, op='perfil'):
    """PERFIL o VACIADO. tabs = {'n':3,'w':8,'h':3} deja puentes en los anillos cerrados
    (solo actúan en las pasadas que ya rebasaron la altura del puente). Devuelve (texto, seg)."""
    z_top, safe = _z_levels(material)
    feed, plunge = float(tool['feed']), float(tool['plunge'])
    depth = float(depth)
    depths = _passes(depth, float(tool['pass_depth']))
    tab_n = int((tabs or {}).get('n', 0) or 0)
    tab_w = float((tabs or {}).get('w', 8.0))
    tab_h = min(float((tabs or {}).get('h', 3.0)), depth)
    z_tab = z_top - (depth - tab_h)     # techo del puente
    lines = _header(name, tool, op, depth, len(depths))
    lines += ['G00 Z%s' % _f(safe), 'M03 S%d' % int(float(tool.get('rpm', 18000)))]
    secs = 0.0
    for pts in toolpaths:
        if len(pts) < 2:
            continue
        closed = _is_closed(pts)
        length = _cum(pts)[-1]
        pieces = _split_ring(pts, tab_n, tab_w) if (closed and tab_n > 0) else None
        lines.append('G00 X%s Y%s' % (_f(pts[0][0]), _f(pts[0][1])))
        for d in depths:
            z_cut = z_top - d
            if pieces and z_cut < z_tab - 1e-9:      # esta pasada ya toca los puentes
                z_now = None
                for seg, is_tab in pieces:
                    z_want = z_tab if is_tab else z_cut
                    if z_now is None or abs(z_want - z_now) > 1e-9:
                        lines.append('G01 Z%s F%s' % (_f(z_want), _f(plunge)))
                        z_now = z_want
                    for p in seg[1:]:
                        lines.append('G01 X%s Y%s F%s' % (_f(p[0]), _f(p[1]), _f(feed)))
            else:
                lines.append('G01 Z%s F%s' % (_f(z_cut), _f(plunge)))
                for p in pts[1:]:
                    lines.append('G01 X%s Y%s F%s' % (_f(p[0]), _f(p[1]), _f(feed)))
                if not closed and d != depths[-1]:
                    # trazo abierto: volver al inicio por arriba antes de la siguiente pasada
                    lines.append('G00 Z%s' % _f(safe))
                    lines.append('G00 X%s Y%s' % (_f(pts[0][0]), _f(pts[0][1])))
            secs += (length / feed + float(tool['pass_depth']) / plunge) * 60.0
        lines.append('G00 Z%s' % _f(safe))
    lines += ['M05', 'G00 X0 Y0', 'M30']
    return '\n'.join(lines) + '\n', secs


def build_drill(points, tool, material, depth, name=''):
    """TALADRO con picoteo: baja por pasadas y entre cada una sube a despejar viruta."""
    z_top, safe = _z_levels(material)
    plunge = float(tool['plunge'])
    depth = float(depth)
    depths = _passes(depth, float(tool['pass_depth']))
    lines = _header(name, tool, 'taladro %d puntos' % len(points), depth, len(depths))
    lines += ['G00 Z%s' % _f(safe), 'M03 S%d' % int(float(tool.get('rpm', 18000)))]
    secs = 0.0
    for x, y in points:
        lines.append('G00 X%s Y%s' % (_f(x), _f(y)))
        for i, d in enumerate(depths):
            lines.append('G01 Z%s F%s' % (_f(z_top - d), _f(plunge)))
            if i < len(depths) - 1:
                lines.append('G00 Z%s' % _f(z_top + _PECK_CLEAR))   # picotazo: despeja viruta
            secs += (d / plunge) * 60.0 * 2
        lines.append('G00 Z%s' % _f(safe))
    lines += ['M05', 'G00 X0 Y0', 'M30']
    return '\n'.join(lines) + '\n', secs
