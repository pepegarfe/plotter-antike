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
