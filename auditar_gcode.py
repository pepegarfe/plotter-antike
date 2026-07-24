#!/usr/bin/env python3
"""Auditoría del G-code de Design Studio ANTES del primer corte real.

Genera .tap por el MISMO camino que la app (studio_backend.cnc_build_tap) para una
batería de casos y verifica, con un parser independiente, los invariantes que
protegen a la máquina y a la pieza. Cualquier FALLA se lista al final.
"""
import re
import sys

sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import studio_backend as sb

FALLAS = []
OK = []


def check(nombre, cond, detalle=''):
    (OK if cond else FALLAS).append(f'{nombre}{" — " + detalle if detalle and not cond else ""}')


def sq(x0, y0, w, h):
    return [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h), (x0, y0)]


TOOL = {'id': 't6-2f', 'name': 'Fresa 6mm 2F', 'dia': 6.0, 'pass_depth': 5.0,
        'feed': 3600, 'plunge': 1000, 'rpm': 18000, 'stepover_pct': 40}
MAT_TOP = {'thickness': 15.0, 'z_zero': 'top', 'clearance': 5.0, 'home_end': True}
MAT_BED = {'thickness': 15.0, 'z_zero': 'bed', 'clearance': 5.0, 'home_end': True}

LN_RE = re.compile(r'^(?:\( [^()]* \)|G90 G21 G17|M03 S\d+|M05|M30|G04 P\d+(?:\.\d{1,3})?|G0[01](?: X(-?\d+(?:\.\d{1,3})?))?(?: Y(-?\d+(?:\.\d{1,3})?))?(?: Z(-?\d+(?:\.\d{1,3})?))?(?: F(\d+(?:\.\d{1,3})?))?)$')


def parse(tap, mat, tool, depth, caso, start=0.0):
    """Verifica formato y física del archivo; devuelve los movimientos [x,y,z,rapid]."""
    lines = tap.split('\n')
    check(f'{caso}: termina en newline', tap.endswith('\n'))
    if lines and lines[-1] == '':
        lines = lines[:-1]
    check(f'{caso}: ASCII puro', all(ord(c) < 128 for c in tap))

    thick = mat['thickness']
    z_top = thick if mat['z_zero'] == 'bed' else 0.0
    safe = z_top + mat['clearance']
    z_min_ok = z_top - start - depth - 1e-6

    body = [l for l in lines if not l.startswith('(')]
    check(f'{caso}: arranca G90 G21 G17', body[0] == 'G90 G21 G17')
    check(f'{caso}: sube a Z segura antes del husillo',
          body[1] == 'G00 Z%g' % safe, body[1])
    check(f'{caso}: M03 con S', body[2].startswith('M03 S'))
    check(f'{caso}: recordatorio de Z0 en el encabezado',
          ('( Z0 en la cama' in tap) if mat['z_zero'] == 'bed'
          else ('( Z0 en la cara superior' in tap))
    check(f'{caso}: espera de husillo tras M03 (G04 + respiro aéreo)',
          body[3].startswith('G04 P') and body[4].startswith('G01 Z')
          and body[5] == 'G00 Z%g' % safe or body[5].startswith('G01 Z'),
          str(body[3:6]))
    fin = body[-3:] if mat.get('home_end', True) else body[-2:]
    check(f'{caso}: cierre M05/[home]/M30',
          fin[-1] == 'M30' and fin[0] == 'M05' and
          (not mat.get('home_end', True) or fin[1] == 'G00 X0 Y0'), str(fin))

    # línea por línea: gramática estricta + física
    x = y = None
    z = None
    moves = []
    zmin = 1e9
    malas = []
    for i, ln in enumerate(lines):
        m = LN_RE.match(ln)
        if not m:
            malas.append(ln)
            continue
        if not ln.startswith('G0') or ln.startswith('G04'):
            continue
        rapid = ln.startswith('G00')
        nx = float(m.group(1)) if m.group(1) else x
        ny = float(m.group(2)) if m.group(2) else y
        nz = float(m.group(3)) if m.group(3) else z
        f = float(m.group(4)) if m.group(4) else None
        aereo = (nz is not None and nz >= safe - 1e-9 and
                 (z is None or z >= safe - 1e-9))
        if not rapid:
            # todo G01 lleva F; bajo la Z segura debe ser la F de corte o la de bajada
            if f is None:
                malas.append('G01 sin F: ' + ln)
            elif not aereo and f not in (float(tool['feed']), float(tool['plunge'])):
                malas.append('F desconocida: ' + ln)
            # bajada vertical que ENTRA al material → F de plunge
            if m.group(3) and not m.group(1) and not m.group(2) \
               and not aereo and f != float(tool['plunge']):
                malas.append('bajada vertical sin F de plunge: ' + ln)
        else:
            if f is not None:
                malas.append('G00 con F: ' + ln)
            # un G00 con XY solo puede viajar A SALVO (>= cara del material)
            if (m.group(1) or m.group(2)) and z is not None and z < z_top - 1e-9:
                malas.append(f'G00 XY con la fresa ENTERRADA (z={z}): ' + ln)
        if nz is not None:
            zmin = min(zmin, nz)
            if nz < z_min_ok:
                malas.append(f'Z más hondo que lo pedido ({nz} < {z_top - start - depth}): ' + ln)
        if x is not None and y is not None and z is not None:
            moves.append([x, y, z, nx, ny, nz, rapid])
        x, y, z = nx, ny, nz
    check(f'{caso}: gramática estricta (todas las líneas)', not malas,
          f'{len(malas)} malas, ej: {malas[:3]}')
    return moves, zmin


def caso_perfil():
    pl = {'paths': [sq(20, 20, 100, 100)], 'op': 'profile', 'side': 'outside',
          'direction': 'climb', 'depth': 15.5, 'tool': TOOL, 'material': MAT_TOP,
          'name': 'prueba', 'label': 'perfil',
          'tabs': {'on': True, 'mode': 'n', 'v': 3, 'w': 8.0, 'h': 3.0},
          'ramp': {'on': True, 'type': 'smooth', 'mode': 'angle', 'v': 10}}
    r = sb.cnc_build_tap(pl)
    check('perfil: genera', r.get('ok'), str(r.get('error')))
    if not r.get('ok'):
        return
    moves, zmin = parse(r['tap'], MAT_TOP, TOOL, 15.5, 'perfil')
    # kerf: cuadrado 100×100 en (20,20), fuera, fresa Ø6 → centro de fresa en [17,123]
    xs = [v for mv in moves for v in (mv[0], mv[3]) if not mv[6]]
    ys = [v for mv in moves for v in (mv[1], mv[4]) if not mv[6]]
    check('perfil: compensación exacta (bbox 17..123)',
          abs(min(xs) - 17) < 0.01 and abs(max(xs) - 123) < 0.01 and
          abs(min(ys) - 17) < 0.01 and abs(max(ys) - 123) < 0.01,
          f'bbox=({min(xs):.2f},{min(ys):.2f})-({max(xs):.2f},{max(ys):.2f})')
    check('perfil: fondo = -15.5 exacto', abs(zmin - (-15.5)) < 1e-6, f'zmin={zmin}')
    # pasadas: niveles de fondo z alcanzados en orden, separados ≤ pass_depth
    zl = sorted({round(min(mv[2], mv[5]), 3) for mv in moves if not mv[6]})
    steps = [round(zl[i] - zl[i + 1], 3) for i in range(len(zl) - 1)]
    check('perfil: 4 pasadas de ≤5mm (15.5/5)', all(s <= 5.0 + 1e-6 for s in steps))
    # puentes: en la última pasada hay tramos que SUBEN a z_fondo+3
    lastz = -15.5
    tab_top = lastz + 3.0
    en_tab = [mv for mv in moves
              if not mv[6] and abs(mv[5] - tab_top) < 1e-6 and mv[5] > mv[2]]
    check('perfil: puentes presentes (sube a fondo+3mm)', len(en_tab) >= 3,
          f'subidas a techo de puente: {len(en_tab)}')
    return r['tap']


def caso_bed():
    pl = {'paths': [sq(20, 20, 100, 100)], 'op': 'profile', 'side': 'outside',
          'direction': 'climb', 'depth': 15.0, 'tool': TOOL, 'material': MAT_BED,
          'name': 'prueba', 'label': 'perfil-bed'}
    r = sb.cnc_build_tap(pl)
    check('z_zero=bed: genera', r.get('ok'), str(r.get('error')))
    if not r.get('ok'):
        return
    moves, zmin = parse(r['tap'], MAT_BED, TOOL, 15.0, 'z_zero=bed')
    check('z_zero=bed: fondo = 0 (la cama)', abs(zmin - 0.0) < 1e-6, f'zmin={zmin}')
    check('z_zero=bed: Z segura = 20', 'G00 Z20' in r['tap'])


def caso_dentro_holgura():
    pl = {'paths': [sq(20, 20, 100, 100)], 'op': 'profile', 'side': 'inside',
          'direction': 'climb', 'depth': 5.0, 'allowance': 0.3, 'tool': TOOL,
          'material': MAT_TOP, 'name': 'prueba', 'label': 'dentro'}
    r = sb.cnc_build_tap(pl)
    check('dentro+holgura: genera', r.get('ok'), str(r.get('error')))
    if not r.get('ok'):
        return
    moves, _ = parse(r['tap'], MAT_TOP, TOOL, 5.0, 'dentro+holgura')
    xs = [v for mv in moves for v in (mv[0], mv[3]) if not mv[6]]
    # dentro con holgura +0.3: centro de fresa a 3.3mm dentro de la línea → [23.3,116.7]
    check('dentro+holgura: deja 0.3mm de material',
          abs(min(xs) - 23.3) < 0.01 and abs(max(xs) - 116.7) < 0.01,
          f'x=({min(xs):.2f},{max(xs):.2f})')


def caso_anidado():
    # dona: cuadro 100 con hueco 40 al centro, por FUERA → el hueco se corta ANTES
    pl = {'paths': [sq(20, 20, 100, 100), sq(50, 50, 40, 40)], 'op': 'profile',
          'side': 'outside', 'direction': 'climb', 'depth': 15.0, 'tool': TOOL,
          'material': MAT_TOP, 'name': 'prueba', 'label': 'dona'}
    r = sb.cnc_build_tap(pl)
    check('anidado: genera', r.get('ok'), str(r.get('error')))
    if not r.get('ok'):
        return
    moves, _ = parse(r['tap'], MAT_TOP, TOOL, 15.0, 'anidado')
    # primer ANILLO = movimientos de corte hasta el primer retract a Z segura
    xs_first = []
    for mv in moves:
        if mv[6] and mv[5] is not None and mv[5] >= 4.9 and xs_first:
            break                                            # retract: terminó el primer anillo
        if not mv[6]:
            xs_first += [mv[0], mv[3]]
    # anidado par-impar: hueco de 40 por "fuera" = compensar HACIA el centro del hueco
    check('anidado: el hueco (contorno chico) se corta primero y compensado al centro',
          min(xs_first) >= 52.9 and max(xs_first) <= 87.1,
          f'primer anillo en x=({min(xs_first):.1f},{max(xs_first):.1f})')


def caso_cajeado():
    pl = {'paths': [sq(30, 30, 40, 40)], 'op': 'pocket', 'direction': 'climb',
          'depth': 6.0, 'tool': TOOL, 'material': MAT_TOP, 'name': 'prueba',
          'label': 'cajeado'}
    r = sb.cnc_build_tap(pl)
    check('cajeado: genera', r.get('ok'), str(r.get('error')))
    if not r.get('ok'):
        return
    moves, zmin = parse(r['tap'], MAT_TOP, TOOL, 6.0, 'cajeado')
    xs = [v for mv in moves for v in (mv[0], mv[3]) if not mv[6]]
    ys = [v for mv in moves for v in (mv[1], mv[4]) if not mv[6]]
    # la pared queda EN la línea: centro de fresa a 3mm dentro → [33,67]
    check('cajeado: pared exacta (centro de fresa 33..67)',
          abs(min(xs) - 33) < 0.01 and abs(max(xs) - 67) < 0.01 and
          abs(min(ys) - 33) < 0.01 and abs(max(ys) - 67) < 0.01,
          f'bbox=({min(xs):.2f},{min(ys):.2f})-({max(xs):.2f},{max(ys):.2f})')
    check('cajeado: fondo -6 exacto', abs(zmin - (-6.0)) < 1e-6, f'zmin={zmin}')


def caso_taladro():
    pl = {'paths': [sq(10, 10, 6, 6), sq(80, 80, 6, 6)], 'op': 'drill',
          'depth': 15.5, 'tool': TOOL, 'material': MAT_TOP, 'name': 'prueba',
          'label': 'taladro'}
    r = sb.cnc_build_tap(pl)
    check('taladro: genera', r.get('ok'), str(r.get('error')))
    if not r.get('ok'):
        return
    moves, zmin = parse(r['tap'], MAT_TOP, TOOL, 15.5, 'taladro')
    check('taladro: fondo -15.5', abs(zmin - (-15.5)) < 1e-6, f'zmin={zmin}')
    check('taladro: retrae entre picotazos (Z2 entre bajadas)', 'G00 Z2\n' in r['tap'])
    # centros: (13,13) y (83,83)
    tocados = {(round(mv[3]), round(mv[4])) for mv in moves if mv[6] and mv[3] is not None}
    check('taladro: centros correctos', (13, 13) in tocados and (83, 83) in tocados,
          str(tocados))


def caso_multi():
    j1 = {'paths': [sq(30, 30, 40, 40)], 'op': 'pocket', 'direction': 'climb',
          'depth': 6.0, 'tool': TOOL, 'label': 'cajeado'}
    j2 = {'paths': [sq(20, 20, 100, 100)], 'op': 'profile', 'side': 'outside',
          'direction': 'climb', 'depth': 15.0, 'tool': TOOL, 'label': 'perfil'}
    r = sb.cnc_build_tap({'jobs': [j1, j2], 'material': MAT_TOP, 'name': 'prueba'})
    check('multi-trabajo: genera', r.get('ok'), str(r.get('error')))
    if not r.get('ok'):
        return
    check('multi-trabajo: un solo M03/M05/M30',
          r['tap'].count('M03') == 1 and r['tap'].count('M05') == 1 and
          r['tap'].count('M30') == 1)
    check('multi-trabajo: cajeado antes que perfil',
          r['tap'].index('cajeado') < r['tap'].index('perfil'))
    parse(r['tap'], MAT_TOP, TOOL, 15.0, 'multi')
    return r['tap']


def caso_marcha():
    # tabla de marchas (RPM reales S1-S9): el archivo lleva la MÁS CERCANA a las RPM
    # del preset; campo legado 'gear' sigue valiendo; sin nada → RPM (otros controles)
    tabla = [3000, 6000, 9000, 12000, 15000, 18000, 21000, 24000, 27000]
    mat = dict(MAT_TOP, gears=tabla)
    pl = {'paths': [sq(20, 20, 100, 100)], 'op': 'profile', 'side': 'outside',
          'depth': 5.0, 'tool': TOOL, 'material': mat, 'name': 'x', 'label': 'p'}
    r = sb.cnc_build_tap(pl)
    check('marcha: genera', r.get('ok'), str(r.get('error')))
    if not r.get('ok'):
        return
    check('marcha: 18000 RPM → S6 en esta tabla', '\nM03 S6\n' in r['tap'])
    check('marcha: anotada en el encabezado', 'marcha S6 = 18000 RPM' in r['tap'])
    parse(r['tap'], mat, TOOL, 5.0, 'marcha')
    tool2 = dict(TOOL, rpm=13000)                     # 13000 → S4 (12000) por cercanía
    r2 = sb.cnc_build_tap({**pl, 'tool': tool2})
    check('marcha: 13000 RPM → S4 (cercanía)', '\nM03 S4\n' in r2['tap'])
    r3 = sb.cnc_build_tap({**pl, 'material': dict(MAT_TOP, gear=7)})
    check('marcha legado (gear=7): M03 S7', '\nM03 S7\n' in r3['tap'])
    r4 = sb.cnc_build_tap({**pl, 'material': MAT_TOP})
    check('sin tabla ni marcha: M03 con RPM', '\nM03 S18000\n' in r4['tap'])
    r5 = sb.cnc_build_tap({**pl, 'material': dict(MAT_TOP, gears=[1, 2, 3])})
    check('tabla inválida (3 valores): cae a RPM', '\nM03 S18000\n' in r5['tap'])
    # la tabla REAL del handle de Jose: 8 marchas DESCENDENTES (S1=18000 … S8=11000)
    real = [18000, 17000, 16000, 15000, 14000, 13000, 12000, 11000]
    r6 = sb.cnc_build_tap({**pl, 'material': dict(MAT_TOP, gears=real)})
    check('tabla real A11E: 18000 RPM → S1 (la más rápida)', '\nM03 S1\n' in r6['tap'])
    r7 = sb.cnc_build_tap({**pl, 'tool': dict(TOOL, rpm=14000),
                           'material': dict(MAT_TOP, gears=real)})
    check('tabla real A11E: 14000 RPM → S5', '\nM03 S5\n' in r7['tap'])


def caso_fresas_mezcladas():
    otra = dict(TOOL, id='t3-1f', name='3mm')
    j1 = {'paths': [sq(30, 30, 40, 40)], 'op': 'pocket', 'depth': 6.0, 'tool': TOOL,
          'label': 'a'}
    j2 = {'paths': [sq(20, 20, 100, 100)], 'op': 'profile', 'side': 'outside',
          'depth': 15.0, 'tool': otra, 'label': 'b'}
    r = sb.cnc_build_tap({'jobs': [j1, j2], 'material': MAT_TOP, 'name': 'x'})
    check('fresas distintas: se RECHAZA con aviso claro',
          not r.get('ok') and 'FRESAS DISTINTAS' in (r.get('error') or ''), str(r))


caso_perfil()
caso_bed()
caso_dentro_holgura()
caso_anidado()
caso_cajeado()
caso_taladro()
caso_multi()
caso_marcha()
caso_fresas_mezcladas()


print(f'\n== {len(OK)} verificaciones OK ==')
if FALLAS:
    print(f'\n!! {len(FALLAS)} FALLAS:')
    for f in FALLAS:
        print('  ✘', f)
    sys.exit(1)
print('   sin fallas')
