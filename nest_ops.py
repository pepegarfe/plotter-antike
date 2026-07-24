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


def _free_at(gb, minx, miny, w, h, x, y, placed):
    bbox = (x, y, x + w, y + h)
    hit = False
    for pg, pb in placed:
        if _bb_overlap(bbox, pb):
            hit = True
            break
    if not hit:
        return True                                # zona limpia: ni hace falta shapely
    moved = affinity.translate(gb, x - minx, y - miny)
    return not _collides(moved, bbox, placed)


def _blf_position(gb, W, H, margin, placed, roll=False):
    """Primera posición libre. roll=False: abajo-izquierda (hoja). roll=True:
    IZQUIERDA-abajo (rollo: llenar el ancho primero, avanzar lo mínimo a lo largo).
    Candidatos por ESQUINAS de lo ya puesto (apretado) + rejilla de respaldo."""
    minx, miny, maxx, maxy = gb.bounds
    w, h = maxx - minx, maxy - miny
    if w > W - 2 * margin + 1e-9 or h > H - 2 * margin + 1e-9:
        return None
    # 1) candidatos pegados a las piezas existentes (y al margen)
    xs, ys = {margin}, {margin}
    for pg, pb in placed:
        xs.add(pb[2]); xs.add(pb[0] - w)
        ys.add(pb[3]); ys.add(pb[1] - h)
    cands = []
    for cx in xs:
        if cx < margin - 1e-9 or cx + w > W - margin + 1e-9:
            continue
        for cy in ys:
            if cy < margin - 1e-9 or cy + h > H - margin + 1e-9:
                continue
            cands.append((cx, cy))
    cands.sort(key=(lambda c: (c[0], c[1])) if roll else (lambda c: (c[1], c[0])))
    for (cx, cy) in cands:
        if _free_at(gb, minx, miny, w, h, cx, cy, placed):
            return (cx, cy)
    # 2) rejilla de respaldo (por si el hueco no toca ninguna esquina)
    step = max(2.0, min(w, h) / 4.0)
    if roll:
        x = margin
        while x + w <= W - margin + 1e-9:
            y = margin
            while y + h <= H - margin + 1e-9:
                if _free_at(gb, minx, miny, w, h, x, y, placed):
                    return (x, y)
                y += step
            x += step
    else:
        y = margin
        while y + h <= H - margin + 1e-9:
            x = margin
            while x + w <= W - margin + 1e-9:
                if _free_at(gb, minx, miny, w, h, x, y, placed):
                    return (x, y)
                x += step
            y += step
    return None


def _slide(gb, x, y, W, H, margin, placed, roll=False):
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

    for _ in range(3):                             # tres vueltas de compactación
        primero_x = roll                           # rollo: primero ← (comer menos material)
        for eje in ((0, 1) if primero_x else (1, 0)):
            if eje == 1:                           # bajar ↓
                lo, hi = 0.0, y - margin
                for _ in range(9):
                    mid = (lo + hi) / 2
                    if free(x, y - mid):
                        lo = mid
                    else:
                        hi = mid
                y -= lo
            else:                                  # izquierda ←
                lo, hi = 0.0, x - margin
                for _ in range(9):
                    mid = (lo + hi) / 2
                    if free(x - mid, y):
                        lo = mid
                    else:
                        hi = mid
                x -= lo
    return x, y


def nest_op(data):
    """Modo síncrono clásico: calcula todo y devuelve el resultado completo."""
    return _nest_core(data, None)


def _nest_core(data, report):
    if not HAS_SHAPELY:
        return {'ok': False, 'error': _NEED}
    o = data or {}
    try:
        W, H = float(o['sheet'][0]), float(o['sheet'][1])
    except Exception:
        return {'ok': False, 'error': 'Falta el tamaño de la hoja.'}
    margin = max(0.0, float(o.get('margin') or 0))
    gap = max(0.0, float(o.get('gap') or 0))
    roll = (o.get('mode') == 'roll')               # rollo (plotter): minimizar el LARGO usado
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
                pos = _blf_position(gb, W, H, margin, pl, roll)
                if pos is None:
                    continue
                clave = (pos[0], pos[1]) if roll else (pos[1], pos[0])
                if best is None or clave < (best[0], best[1]):
                    best = (clave[0], clave[1], r, gb)
            if best is None:
                skipped += 1
                continue
            if roll:
                x0, y0, r, gb = best[0], best[1], best[2], best[3]
            else:
                y0, x0, r, gb = best
            x0, y0 = _slide(gb, x0, y0, W, H, margin, pl, roll)
            minx, miny = gb.bounds[0], gb.bounds[1]
            dx, dy = x0 - minx, y0 - miny
            final = affinity.translate(gb, dx, dy)
            pl.append((final, final.bounds))
            area_ok += u['area']
            results.append({'i': u['i'], 'rot': r, 'dx': dx, 'dy': dy})
        usado = max((b[1][2] for b in pl), default=margin)   # borde derecho: material consumido
        return results, skipped, area_ok, usado

    import time
    t0 = time.time()
    usable = max(1e-9, (W - 2 * margin) * (H - 2 * margin))
    ORDER_LBL = ['área', 'lado mayor', 'lado menor', 'mezcla 1', 'mezcla 2', 'mezcla 3']
    runs = []                                       # bitácora de TODOS los intentos (para animarlos)
    best_run, best_i = None, -1
    for si, rots in enumerate(stages):
        if si > 0 and time.time() - t0 > _BUDGET:   # sin tiempo: quedarse con lo logrado
            break
        paso = int(round(rots[1] - rots[0])) if len(rots) > 1 else 0
        stage_lbl = (str(paso) + '°') if paso else '0°'
        for oi, order in enumerate(orders):
            res = _single(order, rots)
            run = {'stage': stage_lbl, 'order': ORDER_LBL[oi % len(ORDER_LBL)],
                   'placed': res[0], 'skipped': res[1],
                   'util': round(res[2] / usable, 4), 'used': round(res[3], 1)}
            runs.append(run)
            if report:
                report(run)                        # modo EN VIVO: cada intento sale al momento
            if roll:                               # rollo: 1º cuántas caben, 2º MENOS largo usado
                score = (len(res[0]), -res[3], res[2])
            else:                                  # hoja: 1º cuántas caben, 2º área aprovechada
                score = (len(res[0]), res[2], 0)
            if best_run is None or score > best_run[0]:
                best_run = (score, res)
                best_i = len(runs) - 1
    results, skipped, area_ok, usado = best_run[1]

    return {'ok': True, 'placed': results, 'skipped': skipped,
            'util': round(area_ok / usable, 4), 'used': round(usado, 1),
            'runs': runs, 'best': best_i}


# ------------------------------------------------------------------ modo EN VIVO
# nest_start lanza el cálculo en un hilo y devuelve un id; nest_status entrega los
# intentos nuevos desde 'from' y, al terminar, el resultado ganador. La UI sondea
# cada ~300 ms y anima los intentos MIENTRAS el motor sigue trabajando.

_JOBS = {}
_JOB_SEQ = [0]


def nest_start(data):
    if not HAS_SHAPELY:
        return {'ok': False, 'error': _NEED}
    import threading
    _JOB_SEQ[0] += 1
    jid = str(_JOB_SEQ[0])
    job = {'runs': [], 'done': False, 'result': None, 'error': None}
    _JOBS[jid] = job
    for k in list(_JOBS.keys())[:-4]:              # no acumular trabajos viejos
        _JOBS.pop(k, None)

    def work():
        try:
            res = _nest_core(data or {}, lambda run: job['runs'].append(run))
            if res.get('ok'):
                job['result'] = res
            else:
                job['error'] = res.get('error') or 'No se pudo acomodar.'
        except Exception as e:
            job['error'] = str(e)
        job['done'] = True

    threading.Thread(target=work, daemon=True).start()
    return {'ok': True, 'job': jid}


def nest_status(data):
    o = data or {}
    job = _JOBS.get(str(o.get('job') or ''))
    if not job:
        return {'ok': False, 'error': 'Trabajo de acomodo desconocido.'}
    if job['done'] and job['error']:
        return {'ok': False, 'error': job['error']}
    frm = max(0, int(o.get('from') or 0))
    out = {'ok': True, 'runs': job['runs'][frm:], 'done': job['done']}
    if job['done'] and job['result']:
        r = job['result']
        out.update({'placed': r['placed'], 'best': r['best'],
                    'util': r['util'], 'skipped': r['skipped'], 'used': r.get('used')})
    return out

