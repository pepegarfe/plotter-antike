# -*- coding: utf-8 -*-
"""Nesting (acomodo de piezas en la hoja) para Design Studio.

Estado del arte investigado (jul-2026): el óptimo académico usa No-Fit Polygon +
algoritmo genético (SVGnest/Deepnest); el caballo de batalla práctico es el
Bottom-Left-Fill de Burke et al. con piezas grandes primero. libnest2d (C++)
haría NFP exacto pero arrastra Boost/Clipper/NLopt — demasiado para nuestro
empaquetado. Aquí: **BLF greedy con rotaciones + deslizamiento de compactación**
sobre shapely, con pre-filtro de bboxes para que el grueso de las pruebas de
colisión sea aritmética pura.

nest_op(data):
  { 'sheet': [W,H], 'margin': mm, 'gap': mm, 'rots': [0,90,...],
    'units': [ {'rings':[[..pts..]...], 'open':[[..pts..]...], 'pivot':[cx,cy]} ... ],
    'obstacles': [ mismo formato, sin pivot ] }
→ { 'ok': True, 'placed': [ {'i': idx_unidad, 'rot': deg, 'dx': mm, 'dy': mm} ... ],
    'skipped': n, 'util': 0..1 }

La colocación final de la unidad i es: rotar sus puntos alrededor de su 'pivot'
por 'rot' y luego trasladar (dx,dy) — la UI aplica exactamente eso al doc.
"""

import math

try:
    from shapely.geometry import Polygon, LineString, box
    from shapely.ops import unary_union
    from shapely import affinity
    HAS_SHAPELY = True
except Exception:
    HAS_SHAPELY = False

_NEED = 'Falta la librería shapely (pip install shapely).'
_OPEN_W = 0.15     # medio-grosor con el que un trazo abierto gana cuerpo para chocar


def _unit_geom(u):
    """Unidad {rings, open} → geometría shapely (par-impar + líneas con cuerpo)."""
    region = None
    for pts in u.get('rings') or []:
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
    lines = []
    for pts in u.get('open') or []:
        if pts and len(pts) >= 2:
            try:
                lines.append(LineString(pts).buffer(_OPEN_W, quad_segs=4))
            except Exception:
                continue
    if lines:
        region = unary_union(lines + ([region] if region is not None else []))
    return region


def _bb_overlap(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _collides(geom, bbox, placed):
    """¿geom (con su bbox) choca con alguna pieza puesta? bbox primero (barato),
    shapely solo para las candidatas que el bbox no descarta."""
    for pg, pb in placed:
        if _bb_overlap(bbox, pb) and geom.intersects(pg):
            return True
    return False


def _blf_position(gb, W, H, margin, placed):
    """Primera posición libre barriendo de abajo-izquierda (Bottom-Left-Fill)."""
    minx, miny, maxx, maxy = gb.bounds
    w, h = maxx - minx, maxy - miny
    if w > W - 2 * margin + 1e-9 or h > H - 2 * margin + 1e-9:
        return None
    step = max(2.0, min(w, h) / 4.0)
    y = margin
    while y + h <= H - margin + 1e-9:
        x = margin
        while x + w <= W - margin + 1e-9:
            bbox = (x, y, x + w, y + h)
            hit = False
            for pg, pb in placed:
                if _bb_overlap(bbox, pb):
                    hit = True
                    break
            if not hit:
                return (x, y)                      # zona limpia: ni hace falta shapely
            moved = affinity.translate(gb, x - minx, y - miny)
            if not _collides(moved, bbox, placed):
                return (x, y)
            x += step
        y += step
    return None


def _slide(gb, x, y, W, H, margin, placed):
    """Compactación: empuja la pieza hacia abajo y hacia la izquierda con
    bisección (afina más fino que el paso de la rejilla)."""
    minx, miny, maxx, maxy = gb.bounds
    w, h = maxx - minx, maxy - miny

    def free(px, py):
        bbox = (px, py, px + w, py + h)
        if px < margin - 1e-9 or py < margin - 1e-9:
            return False
        moved = affinity.translate(gb, px - minx, py - miny)
        return not _collides(moved, bbox, placed)

    for _ in range(3):                             # abajo ↓ y luego izquierda ←, tres vueltas
        lo, hi = 0.0, y - margin                   # cuánto puede bajar
        for _ in range(9):
            mid = (lo + hi) / 2
            if free(x, y - mid):
                lo = mid
            else:
                hi = mid
        y -= lo
        lo, hi = 0.0, x - margin                   # cuánto puede ir a la izquierda
        for _ in range(9):
            mid = (lo + hi) / 2
            if free(x - mid, y):
                lo = mid
            else:
                hi = mid
        x -= lo
    return x, y


def nest_op(data):
    if not HAS_SHAPELY:
        return {'ok': False, 'error': _NEED}
    o = data or {}
    try:
        W, H = float(o['sheet'][0]), float(o['sheet'][1])
    except Exception:
        return {'ok': False, 'error': 'Falta el tamaño de la hoja.'}
    margin = max(0.0, float(o.get('margin') or 0))
    gap = max(0.0, float(o.get('gap') or 0))
    # 'rots' explícito = modo fijo (compatibilidad/pruebas). Sin 'rots' = AUTOMÁTICO:
    # se prueban 90°→45°→15° como etapas del torneo mientras alcance el presupuesto
    # de tiempo, y gana el mejor acomodo global.
    rots_fijo = o.get('rots')
    if rots_fijo:
        stages = [[float(r) % 360 for r in rots_fijo]]
        if 0 not in stages[0]:
            stages[0] = [0] + stages[0]
    else:
        stages = [[0, 90, 180, 270],
                  list(range(0, 360, 45)),
                  list(range(0, 360, 15))]
    _BUDGET = 5.0                                  # segundos: tope para escalar de etapa

    # obstáculos (piezas bloqueadas): se quedan donde están, engordados por el gap
    placed = []
    for ob in o.get('obstacles') or []:
        g = _unit_geom(ob)
        if g is None or g.is_empty:
            continue
        if gap:
            g = g.buffer(gap / 2.0, quad_segs=8)
        placed.append((g, g.bounds))

    units = []
    for i, u in enumerate(o.get('units') or []):
        g = _unit_geom(u)
        if g is None or g.is_empty:
            continue
        pv = u.get('pivot')
        if not pv:
            b = g.bounds
            pv = [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]
        b = g.bounds
        units.append({'i': i, 'geom': g, 'pivot': (float(pv[0]), float(pv[1])),
                      'area': g.area, 'w': b[2] - b[0], 'h': b[3] - b[1]})
    if not units:
        return {'ok': False, 'error': 'No hay piezas que acomodar.'}

    # MULTI-ARRANQUE: el BLF codicioso depende del ORDEN de entrada; probar varios
    # órdenes completos y quedarse con el mejor nunca empeora (se elige al ganador).
    # (Medido: con hoja apretada, más ángulos por sí solos pueden EMPEORAR — el
    # greedy se auto-bloquea; variar el orden es lo que rescata piezas.)
    import random
    orders = [sorted(units, key=lambda u: -u['area']),
              sorted(units, key=lambda u: -max(u['w'], u['h'])),
              sorted(units, key=lambda u: -min(u['w'], u['h']))]
    rnd = random.Random(20260724)                  # semilla fija: resultado reproducible
    for _ in range(3):
        mix = units[:]
        rnd.shuffle(mix)
        orders.append(mix)

    def _single(order, rots):
        pl = list(placed)                          # arranca con los obstáculos
        results, skipped, area_ok = [], 0, 0.0
        for u in order:
            best = None                            # (y, x, rot, gb)
            for r in rots:
                g = affinity.rotate(u['geom'], r, origin=u['pivot']) if r else u['geom']
                gb = g.buffer(gap / 2.0, quad_segs=8) if gap else g
                pos = _blf_position(gb, W, H, margin, pl)
                if pos is None:
                    continue
                if best is None or (pos[1], pos[0]) < (best[0], best[1]):
                    best = (pos[1], pos[0], r, gb)
            if best is None:
                skipped += 1
                continue
            y0, x0, r, gb = best
            x0, y0 = _slide(gb, x0, y0, W, H, margin, pl)
            minx, miny = gb.bounds[0], gb.bounds[1]
            dx, dy = x0 - minx, y0 - miny
            final = affinity.translate(gb, dx, dy)
            pl.append((final, final.bounds))
            area_ok += u['area']
            results.append({'i': u['i'], 'rot': r, 'dx': dx, 'dy': dy})
        return results, skipped, area_ok

    import time
    t0 = time.time()
    best_run = None
    for si, rots in enumerate(stages):
        if si > 0 and time.time() - t0 > _BUDGET:   # sin tiempo: quedarse con lo logrado
            break
        for order in orders:
            res = _single(order, rots)
            score = (len(res[0]), res[2])          # 1º cuántas caben, 2º área aprovechada
            if best_run is None or score > best_run[0]:
                best_run = (score, res)
    results, skipped, area_ok = best_run[1]

    usable = max(1e-9, (W - 2 * margin) * (H - 2 * margin))
    return {'ok': True, 'placed': results, 'skipped': skipped,
            'util': round(area_ok / usable, 4)}
