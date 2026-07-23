#!/usr/bin/env python3
"""
Servicio del plotter compartido por Design Studio (escritorio y servidor web).

⚠️ SIN VERIFICAR con hardware — construido el 21-jul-2026 sin plotter conectado.
La lógica serial se reutiliza de plotter_control.PlotterController (probada en el original),
pero la comunicación real con el plotter aún NO se ha probado en esta app nueva.

Maneja con gracia la ausencia de plotter: cada método devuelve {'ok':False,'error':...}
en vez de tronar.
"""
import time
import json
import threading

import plotter_control as core


def set_workarea(w, h):
    """Guarda el área de trabajo en la misma config que usa el original."""
    try:
        w, h = float(w), float(h)
        if w < 10 or h < 10:
            return {'ok': False, 'error': 'El área mínima es 10 × 10 mm.'}
        p = core._config_path()
        data = {}
        if p.exists():
            try:
                data = json.loads(p.read_text())
            except Exception:
                data = {}
        data['work_w'] = w
        data['work_h'] = h
        p.write_text(json.dumps(data))
        return {'ok': True, 'work': [w, h]}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def flip_paths_y(paths):
    """Voltea verticalmente (sobre el centro del conjunto) una lista de {'pts':[[x,y],..]}.

    Convención: la UI dibuja Y hacia ARRIBA, y TODO lo que se le entrega debe venir ya en esa
    orientación. El parser SVG entrega Y-abajo (hay que voltear); el de AI ya invierte la Y al
    parsear y el DXF es Y-arriba de nacimiento (NO voltear). ⚠️ El volteo va POR FORMATO aquí
    en el backend — un volteo ciego de todo en la UI fue el bug que puso los .ai/.dxf de cabeza.
    """
    ys = [p[1] for d in paths for p in d['pts']]
    if not ys:
        return paths
    m = min(ys) + max(ys)
    for d in paths:
        d['pts'] = [[p[0], round(m - p[1], 3)] for p in d['pts']]
    return paths


# ===== CNC (RichAuto) — Fase A: máquina, material y biblioteca de fresas =====
# ⚠️ En archivo PROPIO (cnc_config.json), no en plotter_config.json: la app tkinter
# (_save_config en plotter_control.py) sobrescribe ese JSON con solo sus llaves y
# borraría lo nuestro en silencio. Mismo folder que la config del plotter.

def _cnc_path():
    return core._config_path().with_name('cnc_config.json')


# ESQUEMA v2 (estilo Aspire): la fresa es GEOMETRÍA (nombre, Ø, notas) y sus DATOS DE CORTE
# van POR MATERIAL en `cut` — una fresa física, un juego de números por cada material.
# El material activo (material.type) decide qué juego usa el formulario de trayectorias.
# feed/plunge en mm/min; pass_depth = profundidad por pasada; stepover_pct = % del Ø.
_CUT_FIELDS = ('pass_depth', 'feed', 'plunge', 'rpm', 'stepover_pct')

CNC_DEFAULTS = {
    'machine': 'plotter',                              # máquina activa al abrir la app
    'theme': 'light',                                  # tema de la interfaz (claro por default)
    'work': [1220.0, 2440.0],                          # cama de la CNC de Jose (122×244 cm)
    'material': {'thickness': 15.0, 'z_zero': 'top',   # z_zero: 'top' (cara superior) | 'bed' (cama)
                 'clearance': 5.0, 'home_end': True,   # Z segura (mm) y "volver a X0 Y0 al terminar"
                 'type': 'mdf'},                       # material ACTIVO (id de `materials`)
    'materials': [
        {'id': 'mdf', 'name': 'MDF / triplay'},
        {'id': 'acr', 'name': 'Acrílico'},
        {'id': 'pvc', 'name': 'PVC espumado'},
        {'id': 'mad', 'name': 'Madera sólida'},
    ],
    'tool_sel': 't6-2f',
    # Las 5 fresas más comunes de un router de taller, con datos de ARRANQUE por material,
    # basados en tablas de chip load publicadas (feed = RPM × filos × chip load) y práctica
    # de rotulación: MDF ~0.10–0.25 mm/diente; acrílico SIEMPRE mejor con 1 filo (O-flute) y
    # avance alto para no derretir; PVC espumado rápido (3.5–6.5 m/min publicado; aquí
    # conservador) y con menos RPM; madera dura ~0.08–0.20. ⚠️ Son puntos de partida: cada
    # máquina/fresa se afina cortando. Ver .claude/memoria/cnc-richauto.md (fuentes).
    'tools': [
        {'id': 't6-1f', 'name': 'Fresa 6 mm · 1 filo (O-flute)', 'dia': 6.0,
         'notes': 'La reina para acrílico y PVC: un solo filo expulsa la viruta caliente sin derretir el borde.',
         'cut': {
            'mdf': {'pass_depth': 5.0, 'feed': 3000, 'plunge': 900,  'rpm': 18000, 'stepover_pct': 40},
            'acr': {'pass_depth': 3.0, 'feed': 2400, 'plunge': 500,  'rpm': 17000, 'stepover_pct': 40},
            'pvc': {'pass_depth': 8.0, 'feed': 4000, 'plunge': 1200, 'rpm': 14000, 'stepover_pct': 45},
            'mad': {'pass_depth': 4.0, 'feed': 2400, 'plunge': 700,  'rpm': 18000, 'stepover_pct': 40},
         }},
        {'id': 't6-2f', 'name': 'Fresa 6 mm · 2 filos (espiral)', 'dia': 6.0,
         'notes': 'El caballo de batalla en MDF, triplay y madera. En acrílico tiende a derretir: mejor la de 1 filo.',
         'cut': {
            'mdf': {'pass_depth': 5.0, 'feed': 3600, 'plunge': 1000, 'rpm': 18000, 'stepover_pct': 40},
            'acr': {'pass_depth': 2.5, 'feed': 1800, 'plunge': 450,  'rpm': 16000, 'stepover_pct': 35},
            'pvc': {'pass_depth': 6.0, 'feed': 3000, 'plunge': 900,  'rpm': 14000, 'stepover_pct': 45},
            'mad': {'pass_depth': 4.0, 'feed': 2800, 'plunge': 800,  'rpm': 18000, 'stepover_pct': 40},
         }},
        {'id': 't6-comp', 'name': 'Fresa 6 mm · compresión', 'dia': 6.0,
         'notes': 'Para triplay y melamina: borde limpio por AMBAS caras. La primera pasada debe rebasar ~1×Ø de profundidad para que trabaje bien.',
         'cut': {
            'mdf': {'pass_depth': 6.0, 'feed': 3000, 'plunge': 800, 'rpm': 18000, 'stepover_pct': 40},
            'acr': {'pass_depth': 2.5, 'feed': 1500, 'plunge': 400, 'rpm': 16000, 'stepover_pct': 35},
            'pvc': {'pass_depth': 6.0, 'feed': 2500, 'plunge': 800, 'rpm': 14000, 'stepover_pct': 45},
            'mad': {'pass_depth': 5.0, 'feed': 2500, 'plunge': 700, 'rpm': 18000, 'stepover_pct': 40},
         }},
        {'id': 't3-1f', 'name': 'Fresa 3.175 mm (1/8″) · 1 filo', 'dia': 3.175,
         'notes': 'Detalle fino en plásticos y letras chicas. Frágil: no exagerar la pasada.',
         'cut': {
            'mdf': {'pass_depth': 2.5, 'feed': 2000, 'plunge': 600, 'rpm': 18000, 'stepover_pct': 40},
            'acr': {'pass_depth': 1.5, 'feed': 1600, 'plunge': 400, 'rpm': 18000, 'stepover_pct': 40},
            'pvc': {'pass_depth': 3.0, 'feed': 2600, 'plunge': 800, 'rpm': 15000, 'stepover_pct': 45},
            'mad': {'pass_depth': 2.0, 'feed': 1600, 'plunge': 500, 'rpm': 18000, 'stepover_pct': 40},
         }},
        {'id': 't3-2f', 'name': 'Fresa 3.175 mm (1/8″) · 2 filos', 'dia': 3.175,
         'notes': 'Detalle fino en maderas.',
         'cut': {
            'mdf': {'pass_depth': 2.0, 'feed': 2200, 'plunge': 600, 'rpm': 18000, 'stepover_pct': 40},
            'acr': {'pass_depth': 1.2, 'feed': 1200, 'plunge': 350, 'rpm': 16000, 'stepover_pct': 35},
            'pvc': {'pass_depth': 2.5, 'feed': 2200, 'plunge': 700, 'rpm': 15000, 'stepover_pct': 45},
            'mad': {'pass_depth': 1.8, 'feed': 1800, 'plunge': 500, 'rpm': 18000, 'stepover_pct': 40},
         }},
    ],
}

# Migración v1→v2: los presets viejos traían el material EN EL NOMBRE ("Fresa 6 mm · MDF")
# y un solo juego de datos. Se agrupan por (nombre-base, Ø) y cada uno aporta el juego de
# su material; sin palabra clave reconocible, sus datos se copian a TODOS los materiales.
_MAT_KEYWORDS = (('mdf', 'mdf'), ('triplay', 'mdf'), ('acril', 'acr'), ('acríl', 'acr'),
                 ('pvc', 'pvc'), ('espumado', 'pvc'), ('madera', 'mad'))


def _migrate_tools_v1(old_tools, materials):
    mat_ids = [m['id'] for m in materials]
    groups = {}
    for t in old_tools:
        name = str(t.get('name') or 'Fresa')
        low = name.lower()
        mat = next((mid for kw, mid in _MAT_KEYWORDS if kw in low), None)
        base = name
        if mat and '·' in name:
            base = name.rsplit('·', 1)[0].strip()     # "Fresa 6 mm · MDF/triplay" → "Fresa 6 mm"
        cut = {k: float(t.get(k, d)) for k, d in
               zip(_CUT_FIELDS, (3.0, 2000, 500, 18000, 40))}
        key = (base, round(float(t.get('dia', 6.0)), 3))
        g = groups.setdefault(key, {'id': str(t.get('id') or f't{len(groups)}'),
                                    'name': base, 'dia': key[1], 'notes': '', 'cut': {}})
        for mid in ([mat] if mat else mat_ids):       # sin material claro → a todos
            g['cut'].setdefault(mid, dict(cut))
    out = list(groups.values())
    for g in out:                                     # completar materiales faltantes con el 1er juego
        first = next(iter(g['cut'].values()), None)
        for mid in mat_ids:
            if first:
                g['cut'].setdefault(mid, dict(first))
    return out


def cnc_get():
    """Config del CNC completa (defaults + lo guardado encima), migrando esquemas viejos."""
    data = json.loads(json.dumps(CNC_DEFAULTS))   # copia profunda de los defaults
    try:
        p = _cnc_path()
        if p.exists():
            saved = json.loads(p.read_text())
            for k in ('machine', 'theme', 'work', 'material', 'materials', 'tool_sel', 'tools'):
                if k in saved:
                    data[k] = saved[k]
            data['material'] = {**CNC_DEFAULTS['material'], **(data.get('material') or {})}
            if data['tools'] and 'cut' not in data['tools'][0]:      # esquema v1 → migrar
                data['tools'] = _migrate_tools_v1(data['tools'], data['materials'])
                if not any(t['id'] == data['tool_sel'] for t in data['tools']):
                    data['tool_sel'] = data['tools'][0]['id']
                p.write_text(json.dumps({k: data[k] for k in
                                         ('machine', 'theme', 'work', 'material', 'materials',
                                          'tool_sel', 'tools')}, ensure_ascii=False, indent=1))
            if not any(m['id'] == data['material'].get('type') for m in data['materials']):
                data['material']['type'] = data['materials'][0]['id']
    except Exception:
        pass
    data['ok'] = True
    return data


def cnc_set(patch):
    """Aplica un cambio parcial (solo las llaves presentes) y persiste. Devuelve la config completa."""
    try:
        patch = patch or {}
        cur = cnc_get()
        cur.pop('ok', None)
        if 'machine' in patch:
            if patch['machine'] not in ('plotter', 'cnc'):
                return {'ok': False, 'error': 'Máquina desconocida.'}
            cur['machine'] = patch['machine']
        if 'theme' in patch:
            if patch['theme'] not in ('light', 'dark'):
                return {'ok': False, 'error': 'Tema desconocido.'}
            cur['theme'] = patch['theme']
        if 'work' in patch:
            w, h = float(patch['work'][0]), float(patch['work'][1])
            if w < 10 or h < 10:
                return {'ok': False, 'error': 'El área mínima es 10 × 10 mm.'}
            cur['work'] = [w, h]
        if 'materials' in patch:
            mats = []
            for m in (patch['materials'] or []):
                nm = str(m.get('name') or '').strip()
                if nm:
                    mats.append({'id': str(m.get('id') or f'm{len(mats)}'), 'name': nm})
            if not mats:
                return {'ok': False, 'error': 'Debe quedar al menos un material.'}
            cur['materials'] = mats
        mat_ids = [m['id'] for m in cur['materials']]
        if 'material' in patch:
            m = patch['material'] or {}
            old = cur['material']
            t = float(m.get('thickness', old['thickness']))
            if not (0 < t <= 500):
                return {'ok': False, 'error': 'Grosor de material fuera de rango (0–500 mm).'}
            zz = m.get('z_zero', old['z_zero'])
            if zz not in ('top', 'bed'):
                return {'ok': False, 'error': 'Cero de Z inválido.'}
            cl = float(m.get('clearance', old.get('clearance', 5.0)))
            if not (1 <= cl <= 200):
                return {'ok': False, 'error': 'La Z segura debe estar entre 1 y 200 mm.'}
            cur['material'] = {'thickness': t, 'z_zero': zz, 'clearance': cl,
                               'home_end': bool(m.get('home_end', old.get('home_end', True))),
                               'type': str(m.get('type', old.get('type', mat_ids[0])))}
        if cur['material'].get('type') not in mat_ids:
            cur['material']['type'] = mat_ids[0]
        if 'tools' in patch:
            tools = []
            for t in (patch['tools'] or []):
                cut = {}
                for mid, c in (t.get('cut') or {}).items():
                    if mid not in mat_ids:
                        continue                      # datos de un material borrado: se podan
                    cut[mid] = {
                        'pass_depth': max(0.1, float(c.get('pass_depth', 3.0))),
                        'feed': max(1, float(c.get('feed', 2000))),
                        'plunge': max(1, float(c.get('plunge', 500))),
                        'rpm': max(0, float(c.get('rpm', 18000))),
                        'stepover_pct': min(90, max(10, float(c.get('stepover_pct') or 40))),
                    }
                if not cut:
                    cut = {mat_ids[0]: {'pass_depth': 3.0, 'feed': 2000, 'plunge': 500,
                                        'rpm': 18000, 'stepover_pct': 40}}
                tools.append({
                    'id': str(t.get('id') or f't{len(tools)}'),
                    'name': str(t.get('name') or 'Fresa'),
                    'dia': max(0.1, float(t.get('dia', 6.0))),
                    'notes': str(t.get('notes') or ''),
                    'cut': cut,
                })
            if not tools:
                return {'ok': False, 'error': 'Debe quedar al menos una fresa.'}
            cur['tools'] = tools
        if 'tool_sel' in patch:
            cur['tool_sel'] = str(patch['tool_sel'])
        if not any(t['id'] == cur['tool_sel'] for t in cur['tools']):
            cur['tool_sel'] = cur['tools'][0]['id']
        _cnc_path().write_text(json.dumps(cur, ensure_ascii=False, indent=1))
        cur['ok'] = True
        return cur
    except Exception as e:
        return {'ok': False, 'error': str(e)}


# ---- Fases B/C: trayectorias (perfil/cajeado/taladro) y G-code .tap (ver cnc_gcode.py) ----

_NO_CLOSED = ('Ningún trazado cerrado que procesar '
              '(los trazos abiertos solo admiten Perfil "Sobre la línea").')


def _cnc_make(data):
    """Normaliza el payload de la UI y calcula las trayectorias de la operación pedida.
    Devuelve (op, toolpaths, drills, skipped, tool, material, depth, tabs, name)."""
    import cnc_gcode
    paths = [[(float(p[0]), float(p[1])) for p in pts] for pts in (data.get('paths') or [])]
    if not paths:
        raise ValueError('No hay trazados.')
    tool = data.get('tool') or {}
    material = data.get('material') or {}
    depth = float(data.get('depth') or material.get('thickness') or 15.0)
    op = data.get('op') or 'profile'
    dia = float(tool.get('dia', 6.0))
    direction = 'conv' if data.get('direction') == 'conv' else 'climb'
    allowance = float(data.get('allowance') or 0)
    tps, drills = [], []
    if op == 'pocket':
        step = dia * float(tool.get('stepover_pct') or 40) / 100.0
        tps, skipped = cnc_gcode.make_pocket(paths, dia, step, direction, allowance)
    elif op == 'drill':
        drills, skipped = cnc_gcode.drill_points(paths)
    else:
        op = 'profile'
        side = data.get('side') if data.get('side') in ('outside', 'inside', 'on') else 'outside'
        tps, skipped = cnc_gcode.make_toolpaths(paths, side, dia, direction, allowance,
                                                last_pass=float(data.get('last_pass') or 0),
                                                last_rev=bool(data.get('last_rev')))
    if not tps and not drills:
        raise ValueError(_NO_CLOSED)
    tabs = data.get('tabs') or None
    if tabs and not tabs.get('on', True):
        tabs = None
    if tabs:
        v = float(tabs.get('v', tabs.get('n', 0)) or 0)   # 'n' = formato viejo (cantidad)
        tabs = {'mode': 'dist' if tabs.get('mode') == 'dist' else 'n', 'v': v,
                'w': float(tabs.get('w') or 8), 'h': float(tabs.get('h') or 3)}
        if v <= 0:
            tabs = None
    return (op, tps, drills, skipped, tool, material, depth, tabs,
            _norm_ramp(data.get('ramp')), data.get('name') or 'diseno')


def _norm_ramp(r):
    """True/False (legado) o dict {'on','type','mode','v'} → lo que espera cnc_gcode."""
    if isinstance(r, dict):
        if not r.get('on', True):
            return None
        return {'type': r.get('type', 'smooth'), 'mode': r.get('mode', 'angle'),
                'v': float(r.get('v') or 0) or None}
    return bool(r)


def _as_job(data):
    """Convierte un payload de trayectoria en un job de cnc_gcode.build_jobs()."""
    op, tps, drills, skipped, tool, material, depth, tabs, ramp, name = _cnc_make(data)
    start = max(0.0, float(data.get('start') or 0))
    if op == 'drill':
        job = {'op': 'drill', 'points': drills, 'tool': tool, 'depth': depth, 'start': start,
               'label': data.get('label') or ('taladro %d puntos' % len(drills))}
    else:
        job = {'op': 'contour', 'toolpaths': tps, 'tool': tool, 'depth': depth, 'start': start,
               'tabs': (tabs if op == 'profile' else None), 'ramp': ramp,
               'label': data.get('label') or ('cajeado' if op == 'pocket' else 'perfil')}
    return job, op, tps, drills, skipped, tool, material, name


def cnc_toolpaths_preview(data):
    """Trayectorias para pintar en el lienzo (+ puntos de taladro) + estimación de tiempo."""
    import cnc_gcode
    try:
        job, op, tps, drills, skipped, tool, material, name = _as_job(data)
        _, secs = cnc_gcode.build_jobs([job], material, name)
        flat = [cnc_gcode._rpts(t) for t in tps]   # sin banderas de acabado: el lienzo solo pinta puntos
        return {'ok': True, 'op': op, 'toolpaths': flat, 'drills': drills,
                'dia': float(tool.get('dia', 6.0)), 'skipped': skipped, 'secs': round(secs)}
    except Exception as e:
        return {'ok': False, 'error': f'Trayectorias: {e}'}


def cnc_build_tap(data):
    """El .tap completo. Acepta UNA trayectoria (payload plano) o VARIAS en orden
    (data['jobs'] = lista de payloads; material/name compartidos). Todas las de la
    lista deben usar la MISMA fresa: el RichAuto no tiene cambiador automático."""
    import cnc_gcode
    try:
        raw = data.get('jobs')
        if raw:
            mat, name = data.get('material') or {}, data.get('name') or 'diseno'
            ids = {(j.get('tool') or {}).get('id') or (j.get('tool') or {}).get('name')
                   for j in raw}
            if len(ids) > 1:
                return {'ok': False, 'error':
                        'Las trayectorias activas usan FRESAS DISTINTAS. Exporta un archivo '
                        'por fresa (apaga las otras trayectorias con el ojito) — en la '
                        'máquina se cambia la fresa y se vuelve a fijar el cero de Z.'}
            jobs, skipped = [], 0
            for j in raw:
                try:
                    job, _, _, _, sk, _, _, _ = _as_job({**j, 'material': mat, 'name': name})
                except Exception as e:
                    return {'ok': False, 'error': f"{j.get('label') or 'trayectoria'}: {e}"}
                jobs.append(job)
                skipped += sk
            tap, secs = cnc_gcode.build_jobs(jobs, mat, name)
        else:
            job, _, _, _, skipped, _, mat, name = _as_job(data)
            tap, secs = cnc_gcode.build_jobs([job], mat, name)
        return {'ok': True, 'tap': tap, 'lines': tap.count('\n'),
                'skipped': skipped, 'secs': round(secs)}
    except Exception as e:
        return {'ok': False, 'error': f'G-code: {e}'}


def build_hpgl(data):
    """Genera HPGL desde trazados efectivos (mm) + parámetros de corte."""
    conv = core.HPGLConverter(
        speed=int(float(data.get('speed', 320))),
        pressure=int(float(data.get('pressure', 140))),
        overcut_mm=float(data.get('overcut', 0.0)),
        corner_angle_deg=float(data.get('corner', 0.0)))
    conv.initialize()
    for p in data.get('paths', []):
        conv.add_path([(float(pt[0]), float(pt[1])) for pt in p])
    conv.finalize()
    return conv.get_hpgl()


class PlotterService:
    def __init__(self):
        self.ctrl = core.PlotterController()
        self.port = None
        self.baud = 9600
        self._thread = None
        self._abort = False
        self._prog = {'active': False, 'sent': 0, 'total': 0, 'done': False,
                      'error': None, 'cancelled': False}

    # --- estado / puertos ---
    def ports(self):
        try:
            return {'ok': True, 'ports': self.ctrl.get_ports(), 'has_serial': core.HAS_SERIAL}
        except Exception as e:
            return {'ok': False, 'error': str(e), 'ports': []}

    def status(self):
        return {'ok': True, 'connected': bool(self.ctrl.connected),
                'port': self.port, 'baud': self.baud, 'has_serial': core.HAS_SERIAL}

    # --- conexión ---
    def connect(self, port, baud=9600):
        if not port:
            return {'ok': False, 'error': 'Elige un puerto primero.'}
        try:
            self.ctrl.connect(port, int(baud))
            self.port, self.baud = port, int(baud)
            try:
                self.ctrl.send('IN;')
            except Exception:
                pass
            return self.status()
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo conectar: {e}'}

    def disconnect(self):
        try:
            self.ctrl.disconnect()
        except Exception:
            pass
        return self.status()

    # --- control manual ---
    def _guard(self):
        return None if self.ctrl.connected else {'ok': False, 'error': 'Plotter no conectado'}

    def jog(self, direction, dist):
        g = self._guard()
        if g:
            return g
        if direction not in ('up', 'down', 'left', 'right'):
            return {'ok': False, 'error': 'Dirección inválida'}
        try:
            self.ctrl.move_relative(direction, float(dist))
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def pen(self, down):
        g = self._guard()
        if g:
            return g
        try:
            self.ctrl.send('PD;' if down else 'PU;')
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def command(self, which):
        g = self._guard()
        if g:
            return g
        cmd = {'origin': 'PS;', 'home': 'PU0,0;'}.get(which)
        if not cmd:
            return {'ok': False, 'error': 'Comando desconocido'}
        try:
            self.ctrl.send(cmd)
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    # --- envío del corte (hilo de fondo + progreso) ---
    def send_design(self, data):
        g = self._guard()
        if g:
            return g
        if self._prog['active']:
            return {'ok': False, 'error': 'Ya hay un envío en curso'}
        try:
            hpgl = build_hpgl(data)
        except Exception as e:
            return {'ok': False, 'error': f'HPGL: {e}'}
        self._abort = False
        self._prog = {'active': True, 'sent': 0, 'total': 0, 'done': False,
                      'error': None, 'cancelled': False}
        lines = [l.strip() for l in hpgl.split('\n') if l.strip()]
        self._prog['total'] = len(lines)

        def run():
            try:
                for i, line in enumerate(lines):
                    if self._abort:
                        self._prog['cancelled'] = True
                        break
                    self.ctrl.send(line)
                    time.sleep(0.01)
                    self._prog['sent'] = i + 1
            except Exception as e:
                self._prog['error'] = str(e)
            finally:
                self._prog['active'] = False
                self._prog['done'] = True

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return {'ok': True, 'total': len(lines)}

    def progress(self):
        p = dict(self._prog)
        p['ok'] = True
        return p

    def cancel(self):
        self._abort = True
        try:
            self.ctrl.abort()
        except Exception:
            pass
        return {'ok': True}

    def test_cut(self, size_mm=10):
        g = self._guard()
        if g:
            return g
        try:
            conv = core.HPGLConverter(speed=200, pressure=140)
            hpgl = conv.test_square(size_mm)
            return self.send_design({'paths': [], 'speed': 200, 'pressure': 140,
                                     '_raw_hpgl': hpgl}) if False else self._send_raw(hpgl)
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _send_raw(self, hpgl):
        if self._prog['active']:
            return {'ok': False, 'error': 'Ya hay un envío en curso'}
        self._abort = False
        lines = [l.strip() for l in hpgl.split('\n') if l.strip()]
        self._prog = {'active': True, 'sent': 0, 'total': len(lines), 'done': False,
                      'error': None, 'cancelled': False}

        def run():
            try:
                for i, line in enumerate(lines):
                    if self._abort:
                        self._prog['cancelled'] = True
                        break
                    self.ctrl.send(line)
                    time.sleep(0.01)
                    self._prog['sent'] = i + 1
            except Exception as e:
                self._prog['error'] = str(e)
            finally:
                self._prog['active'] = False
                self._prog['done'] = True

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return {'ok': True, 'total': len(lines)}


# Instancia única compartida
SERVICE = PlotterService()
