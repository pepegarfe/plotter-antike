#!/usr/bin/env python3
"""
Trayectorias de corte y G-code (.tap) para la CNC RichAuto — Fases B/C/D/E de Design Studio.

Recibe los trazados EFECTIVOS del diseño (mm, Y hacia arriba) y produce:
- make_toolpaths(): PERFIL compensado (fuera/dentro/sobre la línea) con anidado tipo "O".
- make_pocket(): CAJEADO por anillos concéntricos, zona por zona, del centro a la pared.
- drill_points(): TALADRO en el centro de cada contorno cerrado.
- build_jobs(): el .tap de UNA O VARIAS trayectorias en orden (todas con la MISMA fresa —
  el RichAuto no tiene cambiador automático; con fresas distintas se exporta por separado).

ORDEN DE CORTE (Fase D): huecos antes que el contorno que suelta la pieza; piezas por vecino
más próximo; cada anillo arranca en su vértice más cercano a la posición actual.

PUENTES (tabs): por cantidad o "uno cada X mm"; RAMPEADOS (pendiente 1:2) — la fresa sube y
baja interpolando XYZ, sin escalones verticales.

ENTRADA EN RAMPA (opcional por trayectoria, con los TRES tipos de Aspire): en vez de hundir
la fresa en vertical, cada pasada desciende avanzando — SUAVE (sobre una distancia o ángulo
dados, repasando el tramo), ZIGZAG (vaivén sobre un tramo corto, para contornos chicos) o
ESPIRAL (la bajada repartida en toda la vuelta + una vuelta plana final). Recomendada para
acrílico y fresas de 1 filo.

Dialecto: solo G00/G01 (sin arcos), G90 G21 G17, avances mm/min, comentarios ASCII puro.
⚠️ El controlador puede IGNORAR F y S de fábrica ("F Read = Ign" en el handle).
Cero de Z: 'top' = cara superior del material, 'bed' = cama (la cara queda en Z=grosor).
"""
import math

try:
    from shapely.geometry import Polygon, LineString
    from shapely.geometry.polygon import orient
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

_CLOSE_TOL = 0.05    # mm: fin ≈ inicio → trazado cerrado
_SAFE_MM = 5.0       # altura de seguridad sobre la cara superior del material
_PECK_CLEAR = 2.0    # mm sobre el material entre picotazos del taladro
_TAB_SLOPE = 2.0     # rampa de los puentes: 2 mm de avance por 1 mm de subida


def _is_closed(pts):
    return (len(pts) >= 4 and
            math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) <= _CLOSE_TOL)


def _d2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


# ---------- orden de corte (Fase D) ----------
# Un "anillo" es una lista de puntos, o una tupla (puntos, es_acabado) cuando la trayectoria
# lleva "última pasada separada": los anillos de acabado se cortan en UNA pasada a fondo.

def _rpts(rg):
    return rg[0] if isinstance(rg, tuple) else rg


def _rfin(rg):
    return rg[1] if isinstance(rg, tuple) else False


def _rot_to_nearest(rg, cur):
    """Re-arranca un anillo cerrado en su vértice más cercano a `cur` (viaje mínimo)."""
    pts = _rpts(rg)
    if not _is_closed(pts):
        return rg
    core = pts[:-1]
    i = min(range(len(core)), key=lambda k: _d2(core[k], cur))
    if i:
        core = core[i:] + core[:i]
    out = core + [[core[0][0], core[0][1]]]
    return (out, _rfin(rg)) if isinstance(rg, tuple) else out


def _order_units(units, start=(0.0, 0.0)):
    """units = piezas; cada pieza = anillos en orden interno fijo (huecos → exterior).
    Vecino más próximo entre piezas + rotación del arranque de cada anillo."""
    cur, out, rem = list(start), [], list(units)
    while rem:
        def entry_d(u):
            ring = _rpts(u[0])
            step = max(1, len(ring) // 48)
            return min(_d2(cur, ring[k]) for k in range(0, len(ring), step))
        bi = min(range(len(rem)), key=lambda k: entry_d(rem[k]))
        for ring in rem.pop(bi):
            ring = _rot_to_nearest(ring, cur)
            out.append(ring)
            cur = _rpts(ring)[-1]
    return out


def _units_from(geom, sign=1.0):
    """Piezas de un Polygon/MultiPolygon: por pieza, HUECOS primero y exterior AL FINAL.
    sign orienta los anillos (+1 = exterior antihorario/huecos horario = CLIMB en corte
    exterior con husillo horario; -1 = lo contrario)."""
    units = []
    for p in getattr(geom, 'geoms', [geom]):
        if p.is_empty or not isinstance(p, Polygon):
            continue
        p = orient(p, sign)
        rings = [[list(c) for c in h.coords] for h in p.interiors]
        rings.append([list(c) for c in p.exterior.coords])
        units.append(rings)
    return units


# ---------- trayectorias ----------

def _closed_region(paths):
    """Región par-impar de los trazados cerrados. (region | None, n_abiertos_saltados)."""
    if not HAS_SHAPELY:
        raise RuntimeError('Falta shapely para compensar la fresa. '
                           'Instálala con: pip install shapely')
    region, skipped = None, 0
    for pts in paths:
        if _is_closed(pts):
            poly = Polygon(pts)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if not poly.is_empty:
                region = poly if region is None else region.symmetric_difference(poly)
        elif len(pts) >= 2:
            skipped += 1
    return region, skipped


def make_toolpaths(paths, side, tool_dia, direction='climb', allowance=0.0,
                   last_pass=0.0, last_rev=False):
    """PERFIL: polilíneas del centro de la fresa, YA ORDENADAS. side: outside|inside|on.
    direction: 'climb' (concordante, el default de Aspire) | 'conv' (convencional).
    allowance: holgura en mm — positiva DEJA material (para acabado), negativa sobrecorta.
    last_pass > 0 = ÚLTIMA PASADA SEPARADA (como Aspire): el desbaste corta dejando esa
    cáscara extra y por cada pieza se añade un anillo de ACABADO a la medida exacta que se
    corre en UNA sola pasada a profundidad completa (last_rev lo recorre al revés)."""
    if side == 'on':
        return _order_on(paths), 0
    if side in ('left', 'right'):
        return _offset_side(paths, side, tool_dia, allowance, last_pass), 0
    region, skipped = _closed_region(paths)
    if region is None:
        return [], skipped
    dist = float(tool_dia) / 2.0 + float(allowance or 0)
    if dist <= 0.05:
        raise ValueError('La holgura negativa se come el radio de la fresa.')
    sign = 1.0 if ((side == 'outside') == (direction != 'conv')) else -1.0
    out = 1 if side == 'outside' else -1
    lp = max(0.0, float(last_pass or 0))
    if lp <= 0:
        offset = region.buffer(out * dist, quad_segs=16)
        return _order_units(_units_from(offset, sign)), skipped
    units = []
    for poly in getattr(region, 'geoms', [region]):     # por pieza: desbaste y LUEGO su acabado
        rough = poly.buffer(out * (dist + lp), quad_segs=16)
        fin = poly.buffer(out * dist, quad_segs=16)
        rings = [(r, False) for u in _units_from(rough, sign) for r in u]
        fsign = -sign if last_rev else sign             # acabado opcionalmente en dirección contraria
        rings += [(r, True) for u in _units_from(fin, fsign) for r in u]
        if rings:
            units.append(rings)
    return _order_units(units), skipped


def _order_on(paths):
    """'Sobre la línea': sin compensar; los contornos más anidados primero, luego NN."""
    closed = [[list(p) for p in pts] for pts in paths if _is_closed(pts) and len(pts) >= 2]
    opens = [[list(p) for p in pts] for pts in paths if not _is_closed(pts) and len(pts) >= 2]
    if not HAS_SHAPELY or len(closed) < 2:
        groups = [closed] if closed else []
    else:
        polys = [Polygon(c) for c in closed]
        polys = [p if p.is_valid else p.buffer(0) for p in polys]
        depth = [sum(1 for j, q in enumerate(polys)
                     if j != i and q.contains(polys[i].representative_point()))
                 for i in range(len(polys))]
        byd = {}
        for i, c in enumerate(closed):
            byd.setdefault(depth[i], []).append(c)
        groups = [byd[d] for d in sorted(byd, reverse=True)]
    out, cur = [], [0.0, 0.0]
    for grp in groups:
        ordered = _order_units([[c] for c in grp], start=tuple(cur))
        out.extend(ordered)
        if ordered:
            cur = ordered[-1][-1]
    if opens:
        out.extend(_order_units([[o] for o in opens], start=tuple(cur)))
    return out


def _offset_side(paths, side, tool_dia, allowance=0.0, last_pass=0.0):
    """IZQUIERDA/DERECHA (estilo Aspire para vectores abiertos): desplaza el centro de la
    fresa medio diámetro al lado elegido DE LA DIRECCIÓN DE DIBUJO del trazo (las flechas
    de la vista previa la enseñan). Aplica a abiertos Y cerrados (en cerrados, el lado
    depende del sentido del anillo). Conserva la dirección original del trazo."""
    if not HAS_SHAPELY:
        raise RuntimeError('Falta shapely para compensar la fresa. '
                           'Instálala con: pip install shapely')
    sgn = 1.0 if side == 'left' else -1.0
    dist = float(tool_dia) / 2.0 + float(allowance or 0)
    if dist <= 0.05:
        raise ValueError('La holgura negativa se come el radio de la fresa.')

    def off(d):
        outs = []
        for pts in paths:
            if len(pts) < 2:
                continue
            try:
                oc = LineString(pts).offset_curve(sgn * d, quad_segs=16)
            except Exception:
                continue
            for g in getattr(oc, 'geoms', [oc]):
                c = [list(q) for q in g.coords]
                if len(c) < 2:
                    continue
                if _d2(c[0], pts[0]) > _d2(c[-1], pts[0]):
                    c.reverse()                     # conservar la dirección del dibujo
                outs.append(c)
        return outs

    lp = max(0.0, float(last_pass or 0))
    if lp <= 0:
        return _order_units([[c] for c in off(dist)])
    rings = [(c, False) for c in off(dist + lp)] + [(c, True) for c in off(dist)]
    return _order_units([[r] for r in rings])


def make_pocket(paths, tool_dia, stepover_mm, direction='climb', allowance=0.0):
    """CAJEADO: anillos concéntricos; cada zona completa (centro → pared), zonas por NN.
    allowance positiva deja material en la pared (pasada de acabado aparte)."""
    region, skipped = _closed_region(paths)
    if region is None:
        return [], skipped
    r = float(tool_dia) / 2.0 + float(allowance or 0)
    if r <= 0.05:
        raise ValueError('La holgura negativa se come el radio de la fresa.')
    step = max(0.5, float(stepover_mm))
    sign = -1.0 if direction != 'conv' else 1.0     # cortar por dentro: climb = anillo horario
    units = []
    for poly in getattr(region, 'geoms', [region]):
        levels, k = [], 0
        while True:
            off = poly.buffer(-(r + k * step), quad_segs=16)
            if off.is_empty:
                break
            levels.append(_rings_flat(off, sign))
            k += 1
        rings = []
        for lev in reversed(levels):
            rings.extend(lev)
        if rings:
            units.append(rings)
    return _order_units(units), skipped


def _rings_flat(geom, sign=1.0):
    out = []
    for p in getattr(geom, 'geoms', [geom]):
        if p.is_empty or not isinstance(p, Polygon):
            continue
        p = orient(p, sign)
        out.append([list(c) for c in p.exterior.coords])
        for hole in p.interiors:
            out.append([list(c) for c in hole.coords])
    return out


def drill_points(paths):
    """TALADRO: centro (del bbox) de cada contorno cerrado, en orden NN."""
    pts, skipped = [], 0
    for p in paths:
        if _is_closed(p):
            xs = [q[0] for q in p]
            ys = [q[1] for q in p]
            pts.append([(min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0])
        elif len(p) >= 2:
            skipped += 1
    out, cur = [], [0.0, 0.0]
    while pts:
        i = min(range(len(pts)), key=lambda k: _d2(cur, pts[k]))
        cur = pts.pop(i)
        out.append(cur)
    return out, skipped


# ---------- geometría de arco ----------

def _cum(pts):
    c = [0.0]
    for i in range(1, len(pts)):
        c.append(c[-1] + math.hypot(pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1]))
    return c


def _point_at(pts, cum, s):
    for i in range(1, len(pts)):
        if cum[i] >= s - 1e-9:
            seg = cum[i] - cum[i-1]
            t = 0.0 if seg <= 1e-12 else (s - cum[i-1]) / seg
            return [pts[i-1][0] + (pts[i][0] - pts[i-1][0]) * t,
                    pts[i-1][1] + (pts[i][1] - pts[i-1][1]) * t]
    return [pts[-1][0], pts[-1][1]]


# ---------- puentes ----------

def _tab_count(perim, tabs):
    if tabs.get('mode') == 'dist':
        return max(2, int(math.ceil(perim / max(10.0, float(tabs['v'])))))
    return int(tabs.get('v', tabs.get('n', 0)) or 0)


def _tab_zones(perim, ntabs, tab_w, ramp_len):
    zones = []
    full = tab_w + 2 * ramp_len
    if ntabs < 1 or perim <= ntabs * full * 1.5:
        return None
    for i in range(ntabs):
        c = perim * (i + 0.5) / ntabs
        zones.append((c - full / 2.0, c + full / 2.0))
    return zones


def _tab_z(s, zones, perim, z_cut, z_tab, ramp_len):
    """Altura que imponen los puentes en la posición de arco s (z_cut si no hay puente)."""
    for a, b in zones:
        for sh in (0.0, -perim, perim):      # el puente puede cruzar el empalme del anillo
            aa, bb = a + sh, b + sh
            if aa <= s <= bb:
                up = min(s - aa, bb - s)
                if up >= ramp_len:
                    return z_tab
                return z_cut + (z_tab - z_cut) * (up / ramp_len)
    return z_cut


# ---------- emisión de una pasada (rampa de entrada + puentes unificados) ----------

def _ring_pass(pts, cum, perim, s0, z_from, z_cut, entry_len, zones, z_tab, tab_ramp,
               overlap=True):
    """Vértices [x,y,z] de una pasada de anillo cerrado: arranca en s0, desciende en rampa
    los primeros entry_len mm (si entry_len>0), da la vuelta completa y (si overlap) repasa
    el tramo de rampa a fondo. z = max(rampa, techo de puente). Devuelve (vértices, s_final)."""
    end = s0 + perim + (entry_len if (overlap and entry_len > 0) else 0.0)
    st = {s0, end}
    if entry_len > 0:
        st.add(s0 + entry_len)
    k0, k1 = int(s0 // perim), int(end // perim) + 1
    for k in range(k0, k1 + 1):
        base = k * perim
        for c in cum[:-1]:
            s = c + base
            if s0 - 1e-9 <= s <= end + 1e-9:
                st.add(s)
        if zones:
            for a, b in zones:
                for x in (a, a + tab_ramp, b - tab_ramp, b):
                    s = x + base
                    if s0 - 1e-9 <= s <= end + 1e-9:
                        st.add(s)
    out = []
    for s in sorted(st):
        if entry_len > 0 and s < s0 + entry_len:
            z = z_from + (z_cut - z_from) * ((s - s0) / entry_len)
        else:
            z = z_cut
        if zones:
            z = max(z, _tab_z(s % perim, zones, perim, z_cut, z_tab, tab_ramp))
        p = _point_at(pts, cum, s % perim)
        if out and abs(p[0]-out[-1][0]) < 1e-6 and abs(p[1]-out[-1][1]) < 1e-6 \
               and abs(z-out[-1][2]) < 1e-6:
            continue
        out.append([p[0], p[1], z])
    return out, (s0 + entry_len) % perim if (overlap and entry_len > 0) else s0 % perim


# ---------- rampa de entrada (estilo Aspire: Suave / Zigzag / Espiral, por ángulo o distancia) ----------

def _ramp_cfg(ramp):
    """Normaliza el parámetro ramp: True (legado) = suave a ~11°; dict = {'type','mode','v'}."""
    if not ramp:
        return None
    if ramp is True:
        return {'type': 'smooth', 'mode': 'angle', 'v': 11.3}
    t = ramp.get('type', 'smooth')
    m = ramp.get('mode', 'angle')
    v = float(ramp.get('v') or (10.0 if m == 'angle' else 25.0))
    return {'type': t if t in ('smooth', 'zigzag', 'spiral') else 'smooth', 'mode': m, 'v': v}


def _entry_len(cfg, dz, perim):
    """Largo horizontal de la rampa suave según ángulo o distancia."""
    if cfg['mode'] == 'dist':
        L = cfg['v']
    else:
        ang = max(1.0, min(45.0, cfg['v']))
        L = dz / math.tan(math.radians(ang))
    return max(1.0, min(perim, L))


def _zigzag_pass(pts, cum, perim, s0, z_from, z_cut, cfg, zones, z_tab, tab_ramp):
    """Baja en vaivén sobre un tramo corto y devuelve (vértices, s_final). Después de esto
    se corta la vuelta completa a fondo (que repasa el tramo del vaivén)."""
    dz = z_from - z_cut
    if cfg['mode'] == 'dist':
        L = max(2.0, min(perim / 3.0, cfg['v']))
        slope = math.tan(math.radians(10.0))
    else:
        ang = max(1.0, min(45.0, cfg['v']))
        slope = math.tan(math.radians(ang))
        L = max(2.0, min(perim / 3.0, dz / (2.0 * slope)))
    n = max(2, int(math.ceil(dz / (L * slope))))
    drop = dz / n
    out = []
    z = z_from
    fwd = True
    for _ in range(n):
        a, b = (s0, s0 + L) if fwd else (s0 + L, s0)
        # estaciones del tramo (vértices del anillo dentro del leg + extremos)
        st = sorted({round(c, 6) for c in cum[:-1] if min(a, b) - 1e-9 <= c <= max(a, b) + 1e-9}
                    | {a, b}, reverse=not fwd)
        z_a, z_b = z, z - drop
        for s in st:
            t = abs(s - a) / L
            zz = z_a + (z_b - z_a) * t
            if zones:
                zz = max(zz, _tab_z(s % perim, zones, perim, z_cut, z_tab, tab_ramp))
            p = _point_at(pts, cum, s % perim)
            if out and abs(p[0]-out[-1][0]) < 1e-6 and abs(p[1]-out[-1][1]) < 1e-6 \
                   and abs(zz-out[-1][2]) < 1e-6:
                continue
            out.append([p[0], p[1], zz])
        z -= drop
        fwd = not fwd
    return out, (s0 if fwd else s0 + L) % perim


# ---------- G-code ----------

def _passes(depth, pass_depth):
    n = max(1, math.ceil(depth / max(0.1, pass_depth)))
    return [min(depth, pass_depth * (i + 1)) for i in range(n)]


def _f(v):
    s = ('%.3f' % v).rstrip('0').rstrip('.')
    return s if s not in ('-0', '') else '0'


def _ascii(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode('ascii')
    return ''.join(c if c.isprintable() and c not in '()' else ' ' for c in s).strip()


def gear_for(rpm, gears):
    """Marcha S<n> cuya RPM real (tabla del handle/variador) queda más cerca de `rpm`.
    0 si no hay tabla válida (8 marchas en el A11E de Jose; se aceptan 8 o 9)."""
    try:
        g = [float(x) for x in (gears or [])]
    except (TypeError, ValueError):
        return 0
    if len(g) not in (8, 9) or any(x <= 0 for x in g):
        return 0
    r = float(rpm or 0)
    return min(range(len(g)), key=lambda i: abs(g[i] - r)) + 1


def _z_levels(material):
    thick = float(material.get('thickness', 15.0))
    z_top = thick if material.get('z_zero') == 'bed' else 0.0
    clear = float(material.get('clearance', _SAFE_MM) or _SAFE_MM)   # "Z segura" configurable
    return z_top, z_top + clear


def _contour_body(lines, toolpaths, tool, depth, tabs, ramp, z_top, safe, start=0.0):
    """Emite perfil/cajeado. `start` = prof. inicial (el corte va de start a start+depth).
    Devuelve segundos estimados."""
    feed, plunge = float(tool['feed']), float(tool['plunge'])
    depth = float(depth)
    start = max(0.0, float(start or 0))
    z_start = z_top - start                       # de aquí hacia abajo se corta
    depths = _passes(depth, float(tool['pass_depth']))
    tabs = tabs or {}
    tab_w = float(tabs.get('w', 8.0))
    tab_h = min(float(tabs.get('h', 3.0)), depth)
    z_tab = z_start - (depth - tab_h)             # techo del puente (desde el fondo real)
    tab_ramp = tab_h * _TAB_SLOPE
    rcfg = _ramp_cfg(ramp)
    secs = 0.0
    for rg in toolpaths:
        pts = _rpts(rg)
        if len(pts) < 2:
            continue
        finish = _rfin(rg)                # anillo de acabado: UNA pasada a profundidad completa
        ring_depths = [depths[-1]] if finish else depths
        closed = _is_closed(pts)
        cum = _cum(pts)
        perim = cum[-1]
        zones = None
        if closed and tabs:
            n = _tab_count(perim, tabs)
            if n > 0:
                zones = _tab_zones(perim, n, tab_w, tab_ramp)
        lines.append('G00 X%s Y%s' % (_f(pts[0][0]), _f(pts[0][1])))
        s_cur, z_prev, z_now = 0.0, z_start, None   # z_now = altura real de la fresa (None = arriba)
        rc = rcfg if closed else None
        for d in ring_depths:
            z_cut = z_start - d
            dz = z_prev - z_cut
            pass_zones = zones if (zones and z_cut < z_tab - 1e-9) else None
            rtype = rc['type'] if (rc and dz > 1e-9) else None
            if rtype == 'zigzag':
                # vaivén descendente y luego la vuelta completa a fondo (repasa el tramo)
                verts, s_zz = _zigzag_pass(pts, cum, perim, s_cur, z_prev, z_cut,
                                           rc, pass_zones, z_tab, tab_ramp)
                lap, s_cur = _ring_pass(pts, cum, perim, s_zz, z_cut, z_cut,
                                        0.0, pass_zones, z_tab, tab_ramp)
                verts += lap
            elif rtype == 'spiral':
                # la bajada repartida en TODA la vuelta; la vuelta plana final la da el cierre
                verts, s_cur = _ring_pass(pts, cum, perim, s_cur, z_prev, z_cut,
                                          perim, pass_zones, z_tab, tab_ramp, overlap=False)
            elif rtype == 'smooth':
                verts, s_cur = _ring_pass(pts, cum, perim, s_cur, z_prev, z_cut,
                                          _entry_len(rc, dz, perim), pass_zones, z_tab, tab_ramp)
            elif pass_zones:
                verts, s_cur = _ring_pass(pts, cum, perim, s_cur, z_prev, z_cut,
                                          0.0, pass_zones, z_tab, tab_ramp)
            else:
                verts = None
            if verts is not None:
                if z_now is None or abs(verts[0][2] - z_now) > 1e-9:   # no repetir una Z en la que ya está
                    lines.append('G01 Z%s F%s' % (_f(verts[0][2]), _f(plunge)))
                for x, y, z in verts[1:]:
                    lines.append('G01 X%s Y%s Z%s F%s' % (_f(x), _f(y), _f(z), _f(feed)))
                z_now = verts[-1][2]
            else:
                lines.append('G01 Z%s F%s' % (_f(z_cut), _f(plunge)))
                for p in pts[1:]:
                    lines.append('G01 X%s Y%s F%s' % (_f(p[0]), _f(p[1]), _f(feed)))
                if not closed and d != ring_depths[-1]:
                    lines.append('G00 Z%s' % _f(safe))
                    lines.append('G00 X%s Y%s' % (_f(pts[0][0]), _f(pts[0][1])))
                    z_now = None
                else:
                    z_now = z_cut
            z_prev = z_cut
            secs += (perim / feed + float(tool['pass_depth']) / plunge) * 60.0
        if closed and rc and rc['type'] == 'spiral' and not finish:
            z_fin = z_start - ring_depths[-1]
            fzones = zones if (zones and z_fin < z_tab - 1e-9) else None
            verts, s_cur = _ring_pass(pts, cum, perim, s_cur, z_fin, z_fin,
                                      0.0, fzones, z_tab, tab_ramp)
            for x, y, z in verts[1:]:
                lines.append('G01 X%s Y%s Z%s F%s' % (_f(x), _f(y), _f(z), _f(feed)))
            secs += (perim / feed) * 60.0
        lines.append('G00 Z%s' % _f(safe))
    return secs


def _drill_body(lines, points, tool, depth, z_top, safe, start=0.0):
    plunge = float(tool['plunge'])
    depth = float(depth)
    z_start = z_top - max(0.0, float(start or 0))
    depths = _passes(depth, float(tool['pass_depth']))
    secs = 0.0
    for x, y in points:
        lines.append('G00 X%s Y%s' % (_f(x), _f(y)))
        for i, d in enumerate(depths):
            lines.append('G01 Z%s F%s' % (_f(z_start - d), _f(plunge)))
            if i < len(depths) - 1:
                lines.append('G00 Z%s' % _f(z_top + _PECK_CLEAR))
            secs += (d / plunge) * 60.0 * 2
        lines.append('G00 Z%s' % _f(safe))
    return secs


def build_jobs(jobs, material, name=''):
    """El .tap de una lista de trabajos EN ORDEN. Cada job:
    {'op','toolpaths'|'points','tool','depth','tabs'|None,'ramp':bool,'label'}.
    Todos deben usar la MISMA fresa (validarlo antes). Devuelve (texto, segundos)."""
    z_top, safe = _z_levels(material)
    tool = jobs[0]['tool']
    what = jobs[0].get('label', 'perfil') if len(jobs) == 1 else '%d trayectorias' % len(jobs)
    maxd = max(float(j['depth']) for j in jobs)
    # Velocidad del husillo: con tabla de marchas (RPM reales de S1-S9 del variador) se
    # emite S<marcha más cercana a las RPM del preset de la fresa> — es lo que entiende
    # un DSP multi-speed con "S Read = Read S" (el A11E de Jose toma el S como número de
    # marcha; un S18000 ahí es "marcha 18000" → el husillo NO arranca). Sin tabla se
    # emiten las RPM (legado / controles que sí leen RPM).
    rpm = int(float(tool.get('rpm', 18000)))
    gear = gear_for(rpm, material.get('gears'))
    if not gear:
        try:
            g = int(material.get('gear') or 0)      # campo viejo (marcha manual global)
            gear = g if 1 <= g <= 9 else 0
        except (TypeError, ValueError):
            gear = 0
    if gear:
        m03 = 'M03 S%d' % gear
        s_note = 'marcha S%d = %d RPM' % (gear, rpm)   # ⚠️ sin paréntesis: anidados rompen el comentario
    else:
        m03 = 'M03 S%d' % rpm
        s_note = '%d RPM' % rpm
    z_note = ('Z0 en la cama - la cara del material queda en Z%s' % _f(z_top)
              if material.get('z_zero') == 'bed'
              else 'Z0 en la cara superior del material')
    lines = [
        '( %s - Design Studio )' % _ascii(name or 'diseno'),
        '( Fresa: %s / O %s mm / %s / hasta %s mm / %s )' %
        (_ascii(tool.get('name', '?')), _f(float(tool['dia'])), _ascii(what), _f(maxd), s_note),
        '( %s )' % z_note,
        'G90 G21 G17',
        'G00 Z%s' % _f(safe),
        m03,
    ]
    secs = 0.0
    # Espera de arranque del husillo (llegar a sus RPM antes de tocar material).
    # CINTURÓN Y TIRANTES porque la unidad del P de G04 varía por controlador:
    # (1) G04 P<seg> — si el control lo lee en segundos, pausa exacta; en ms, inocuo.
    # (2) Respaldo agnóstico: 4 mm de viaje EN EL AIRE (sobre la Z segura) a una F
    #     calculada para durar exactamente la espera — funciona en cualquier control
    #     que lea F (mismo requisito que ya tiene todo el archivo: "Read F").
    spin = float(material.get('spinup', 10.0) or 0)
    if spin > 0:
        lines.append('( espera husillo %s s )' % _f(spin))
        lines.append('G04 P%s' % _f(spin))
        f_air = max(6.0, 240.0 / spin)
        lines.append('G01 Z%s F%s' % (_f(safe + 2), _f(f_air)))
        lines.append('G01 Z%s F%s' % (_f(safe), _f(f_air)))
        secs += spin
    for j in jobs:
        lines.append('( -- %s -- )' % _ascii(j.get('label', j['op'])))
        if j['op'] == 'drill':
            secs += _drill_body(lines, j['points'], j['tool'], j['depth'], z_top, safe,
                                start=j.get('start', 0.0))
        else:
            secs += _contour_body(lines, j['toolpaths'], j['tool'], j['depth'],
                                  j.get('tabs'), j.get('ramp'), z_top, safe,
                                  start=j.get('start', 0.0))
    lines.append('M05')
    if material.get('home_end', True):        # "posición final": volver al origen (configurable)
        lines.append('G00 X0 Y0')
    lines.append('M30')
    return '\n'.join(lines) + '\n', secs


# --- envolturas de un solo trabajo (compatibilidad con pruebas y backend viejo) ---

def build_gcode(toolpaths, tool, material, depth, name='', tabs=None, op='perfil', ramp=False):
    return build_jobs([{'op': 'contour', 'toolpaths': toolpaths, 'tool': tool,
                        'depth': depth, 'tabs': tabs, 'ramp': ramp, 'label': op}],
                      material, name)


def build_drill(points, tool, material, depth, name=''):
    return build_jobs([{'op': 'drill', 'points': points, 'tool': tool, 'depth': depth,
                        'label': 'taladro %d puntos' % len(points)}], material, name)
