# -*- coding: utf-8 -*-
"""Operaciones de geometría del DISEÑO: booleanas (unir/restar/intersectar) y
contorno-offset. Reciben figuras en mm (coordenadas EFECTIVAS de la UI) y
devuelven anillos nuevos en mm.

Convenciones (las mismas del CAM en cnc_gcode.py):
- Una "unidad" = lista de anillos cerrados que se combinan PAR-IMPAR
  (symmetric_difference): la "O" es letra + hueco, no dos discos.
- Entre unidades: unión. Restar = la PRIMERA unidad menos las demás (la de
  abajo en el orden de dibujo — la UI manda ese orden).

shapely es OPCIONAL (HAS_SHAPELY), igual que en el resto del proyecto.

API:
    boolean_op({'op': 'union'|'difference'|'intersection', 'units': [[[x,y]...]...]})
    offset_op({'dist': mm (+afuera/-adentro), 'units': ídem})
    ambos → {'ok': True, 'paths': [{'pts': [[x,y]...]}...]} | {'ok': False, 'error': ...}
"""

import math

try:
    from shapely.geometry import Polygon, LineString
    from shapely.ops import unary_union, polygonize
    HAS_SHAPELY = True
except Exception:
    HAS_SHAPELY = False

import plotter_control as core   # _simplify_mm: la misma limpieza que usan los parsers

_NEED = 'Falta la librería shapely (pip install shapely).'


def _poly_of_unit(rings):
    """Anillos de una unidad → polígono con anidado par-impar (o None)."""
    region = None
    for pts in rings or []:
        if not pts or len(pts) < 3:
            continue
        try:
            p = Polygon(pts)
            if not p.is_valid:
                p = p.buffer(0)
            if p.is_empty:
                continue
            region = p if region is None else region.symmetric_difference(p)
        except Exception:
            continue
    return region


def _units_polys(units):
    polys = [_poly_of_unit(u) for u in units or []]
    return [p for p in polys if p is not None and not p.is_empty]


def _rings_of(geom):
    """Geometría → lista de anillos {'pts': ...} (exteriores + huecos), simplificados."""
    out = []
    if geom is None or geom.is_empty:
        return out
    geoms = list(getattr(geom, 'geoms', [geom]))
    for g in geoms:
        if g.geom_type != 'Polygon':
            continue
        for ring in [g.exterior] + list(g.interiors):
            pts = [[float(x), float(y)] for x, y in ring.coords]
            pts = core._simplify_mm(pts, 0.003)
            if len(pts) >= 4:                 # triángulo cerrado como mínimo
                out.append({'pts': pts})
    return out


def boolean_op(data):
    if not HAS_SHAPELY:
        return {'ok': False, 'error': _NEED}
    o = data or {}
    op = o.get('op')
    polys = _units_polys(o.get('units'))
    if len(polys) < 2:
        return {'ok': False, 'error': 'Se necesitan al menos dos figuras cerradas.'}
    try:
        if op == 'union':
            res = unary_union(polys)
        elif op == 'difference':
            res = polys[0]
            for p in polys[1:]:
                res = res.difference(p)
        elif op == 'intersection':
            res = polys[0]
            for p in polys[1:]:
                res = res.intersection(p)
        elif op == 'exclude':                # Exclusión: quita los traslapes, deja el resto
            res = polys[0]
            for p in polys[1:]:
                res = res.symmetric_difference(p)
        else:
            return {'ok': False, 'error': 'Operación desconocida.'}
    except Exception as e:
        return {'ok': False, 'error': f'La operación falló: {e}'}
    paths = _rings_of(res)
    if not paths:
        return {'ok': False, 'error': 'La operación dejó un resultado vacío '
                                      '(¿las figuras no se tocan?).'}
    return {'ok': True, 'paths': paths}


def offset_op(data):
    if not HAS_SHAPELY:
        return {'ok': False, 'error': _NEED}
    o = data or {}
    try:
        dist = float(o.get('dist') or 0)
    except Exception:
        dist = 0.0
    if abs(dist) < 0.01:
        return {'ok': False, 'error': 'Da la distancia del contorno (± mm).'}
    polys = _units_polys(o.get('units'))
    if not polys:
        return {'ok': False, 'error': 'Se necesita al menos una figura cerrada.'}
    geom = unary_union(polys)
    # redondeos con sagita ~0.005 mm según la distancia (sin N fijo burdo)
    qs = int(math.pi / 2 / max(1e-6, math.sqrt(2 * 0.005 / abs(dist)))) + 1
    qs = max(16, min(96, qs))
    try:
        off = geom.buffer(dist, quad_segs=qs)
    except Exception as e:
        return {'ok': False, 'error': f'El contorno falló: {e}'}
    paths = _rings_of(off)
    if not paths:
        return {'ok': False, 'error': 'El contorno hacia adentro se comió toda la figura.'}
    return {'ok': True, 'paths': paths}


def _qs_for(radius):
    """Segmentos de redondeo por sagita ~0.005 mm."""
    qs = int(math.pi / 2 / max(1e-6, math.sqrt(2 * 0.005 / max(1e-6, abs(radius))))) + 1
    return max(16, min(96, qs))


def expand_op(data):
    """Engrosar línea: polilíneas ABIERTAS → figura cerrada con grosor total
    `width` (media a cada lado, puntas y uniones redondas)."""
    if not HAS_SHAPELY:
        return {'ok': False, 'error': _NEED}
    o = data or {}
    try:
        width = float(o.get('width') or 0)
    except Exception:
        width = 0.0
    if width < 0.05:
        return {'ok': False, 'error': 'Da el grosor de la línea (mm).'}
    geoms = []
    for pts in o.get('paths') or []:
        if pts and len(pts) >= 2:
            try:
                geoms.append(LineString(pts).buffer(width / 2.0, quad_segs=_qs_for(width / 2.0)))
            except Exception:
                continue
    if not geoms:
        return {'ok': False, 'error': 'Se necesita al menos una línea abierta.'}
    paths = _rings_of(unary_union(geoms))
    if not paths:
        return {'ok': False, 'error': 'No salió ninguna figura.'}
    return {'ok': True, 'paths': paths}


def round_op(data):
    """Esquinas redondeadas con radio r: apertura+cierre morfológicos
    (erosión r → dilatación 2r → erosión r), que redondea esquinas convexas
    Y cóncavas. Cada unidad se procesa APARTE (no une figuras vecinas)."""
    if not HAS_SHAPELY:
        return {'ok': False, 'error': _NEED}
    o = data or {}
    try:
        r = float(o.get('r') or 0)
    except Exception:
        r = 0.0
    if r < 0.05:
        return {'ok': False, 'error': 'Da el radio del redondeo (mm).'}
    qs = _qs_for(r)
    out = []
    comidas = 0
    for u in o.get('units') or []:
        poly = _poly_of_unit(u)
        if poly is None or poly.is_empty:
            continue
        try:
            rounded = poly.buffer(-r, quad_segs=qs).buffer(2 * r, quad_segs=qs).buffer(-r, quad_segs=qs)
        except Exception:
            continue
        rings = _rings_of(rounded)
        if rings:
            out.extend(rings)
        else:
            comidas += 1               # radio más grande que la figura: se devuelve INTACTA
            for pts in u:
                if pts and len(pts) >= 3:
                    out.append({'pts': [[float(x), float(y)] for (x, y) in pts]})
    if not out or comidas == len(o.get('units') or []):
        return {'ok': False, 'error': 'Ese radio se come las figuras enteras — usa uno más chico.'}
    res = {'ok': True, 'paths': out}
    if comidas:
        res['eaten'] = comidas
    return res


def divide_op(data):
    """Dividir (Pathfinder): parte las figuras por TODOS sus cruces; cada carita
    del arreglo queda como pieza independiente (lista de 'faces', cada una con
    sus anillos par-impar)."""
    if not HAS_SHAPELY:
        return {'ok': False, 'error': _NEED}
    polys = _units_polys((data or {}).get('units'))
    if len(polys) < 2:
        return {'ok': False, 'error': 'Se necesitan al menos dos figuras cerradas.'}
    total = unary_union(polys)
    lines = unary_union([p.boundary for p in polys])
    faces = []
    try:
        for f in polygonize(lines):
            rp = f.representative_point()
            if total.covers(rp):                 # solo las caras que SON material
                rings = _rings_of(f)
                if rings:
                    faces.append([r['pts'] for r in rings])
    except Exception as e:
        return {'ok': False, 'error': f'No se pudo dividir: {e}'}
    if len(faces) < 2:
        return {'ok': False, 'error': 'Las figuras no se cruzan — no hay nada que dividir.'}
    return {'ok': True, 'faces': faces}

