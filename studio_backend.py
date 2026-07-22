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


# Presets iniciales por material (puntos de partida sensatos para un router 1220×2440;
# Jose los afina con su máquina). feed/plunge en mm/min, pass_depth = profundidad por pasada.
CNC_DEFAULTS = {
    'machine': 'plotter',                              # máquina activa al abrir la app
    'work': [1220.0, 2440.0],                          # cama de la CNC de Jose (122×244 cm)
    'material': {'thickness': 15.0, 'z_zero': 'top'},  # z_zero: 'top' (cara superior) | 'bed' (cama)
    'tool_sel': 't6-mdf',
    'tools': [
        {'id': 't6-mdf', 'name': 'Fresa 6 mm · MDF/triplay',        'dia': 6.0,   'pass_depth': 5.0, 'feed': 2500, 'plunge': 800,  'rpm': 18000},
        {'id': 't6-acr', 'name': 'Fresa 6 mm · Acrílico',           'dia': 6.0,   'pass_depth': 4.0, 'feed': 1800, 'plunge': 500,  'rpm': 18000},
        {'id': 't6-pvc', 'name': 'Fresa 6 mm · PVC espumado',       'dia': 6.0,   'pass_depth': 8.0, 'feed': 3000, 'plunge': 1000, 'rpm': 16000},
        {'id': 't6-mad', 'name': 'Fresa 6 mm · Madera sólida',      'dia': 6.0,   'pass_depth': 4.0, 'feed': 2000, 'plunge': 600,  'rpm': 18000},
        {'id': 't3-det', 'name': 'Fresa 3.175 mm (1/8″) · Detalle', 'dia': 3.175, 'pass_depth': 2.5, 'feed': 1500, 'plunge': 500,  'rpm': 20000},
    ],
}


def cnc_get():
    """Config del CNC completa (defaults + lo guardado encima)."""
    data = json.loads(json.dumps(CNC_DEFAULTS))   # copia profunda de los defaults
    try:
        p = _cnc_path()
        if p.exists():
            saved = json.loads(p.read_text())
            for k in ('machine', 'work', 'material', 'tool_sel', 'tools'):
                if k in saved:
                    data[k] = saved[k]
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
        if 'work' in patch:
            w, h = float(patch['work'][0]), float(patch['work'][1])
            if w < 10 or h < 10:
                return {'ok': False, 'error': 'El área mínima es 10 × 10 mm.'}
            cur['work'] = [w, h]
        if 'material' in patch:
            m = patch['material'] or {}
            t = float(m.get('thickness', cur['material']['thickness']))
            if not (0 < t <= 500):
                return {'ok': False, 'error': 'Grosor de material fuera de rango (0–500 mm).'}
            zz = m.get('z_zero', cur['material']['z_zero'])
            if zz not in ('top', 'bed'):
                return {'ok': False, 'error': 'Cero de Z inválido.'}
            cur['material'] = {'thickness': t, 'z_zero': zz}
        if 'tools' in patch:
            tools = []
            for t in (patch['tools'] or []):
                tools.append({
                    'id': str(t.get('id') or f't{len(tools)}'),
                    'name': str(t.get('name') or 'Fresa'),
                    'dia': max(0.1, float(t.get('dia', 6.0))),
                    'pass_depth': max(0.1, float(t.get('pass_depth', 3.0))),
                    'feed': max(1, float(t.get('feed', 2000))),
                    'plunge': max(1, float(t.get('plunge', 500))),
                    'rpm': max(0, float(t.get('rpm', 18000))),
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


# ---- Fase B: trayectorias de perfil y G-code .tap (ver cnc_gcode.py) ----

def _cnc_payload(data):
    """Normaliza el payload de la UI: trazados efectivos + fresa + material + corte."""
    paths = [[(float(p[0]), float(p[1])) for p in pts] for pts in (data.get('paths') or [])]
    tool = data.get('tool') or {}
    material = data.get('material') or {}
    depth = float(data.get('depth') or material.get('thickness') or 15.0)
    side = data.get('side') or 'outside'
    if side not in ('outside', 'inside', 'on'):
        side = 'outside'
    return paths, tool, material, depth, side


def cnc_toolpaths_preview(data):
    """Solo las polilíneas del centro de la fresa (para pintarlas en el lienzo) + estimación."""
    import cnc_gcode
    try:
        paths, tool, material, depth, side = _cnc_payload(data)
        if not paths:
            return {'ok': False, 'error': 'No hay trazados.'}
        tps, skipped = cnc_gcode.make_toolpaths(paths, side, float(tool.get('dia', 6.0)))
        if not tps:
            return {'ok': False, 'error': 'Ningún trazado cerrado que compensar '
                                          '(los trazos abiertos solo admiten "Sobre la línea").'}
        _, secs = cnc_gcode.build_gcode(tps, tool, material, depth)
        return {'ok': True, 'toolpaths': tps, 'skipped': skipped, 'secs': round(secs)}
    except Exception as e:
        return {'ok': False, 'error': f'Trayectorias: {e}'}


def cnc_build_tap(data):
    """El archivo .tap completo (texto) listo para guardar/descargar."""
    import cnc_gcode
    try:
        paths, tool, material, depth, side = _cnc_payload(data)
        if not paths:
            return {'ok': False, 'error': 'No hay trazados.'}
        tps, skipped = cnc_gcode.make_toolpaths(paths, side, float(tool.get('dia', 6.0)))
        if not tps:
            return {'ok': False, 'error': 'Ningún trazado cerrado que compensar '
                                          '(los trazos abiertos solo admiten "Sobre la línea").'}
        tap, secs = cnc_gcode.build_gcode(tps, tool, material, depth,
                                          name=data.get('name') or 'diseno')
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
