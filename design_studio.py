#!/usr/bin/env python3
"""
Design Studio — interfaz nueva (web) que REUSA el motor de Plotter Antike.

La cara (HTML/CSS/JS en studio_ui.html) corre dentro de una ventana nativa (pywebview);
la lógica pesada — leer SVG/DXF/AI, generar HPGL, hablar con el plotter — se importa tal
cual de plotter_control.py. No se reescribe el motor, solo la interfaz.
"""
import os
import sys
import json
import webview

import plotter_control as core   # el motor existente (parsers, HPGL, controlador)
from studio_backend import SERVICE, set_workarea as _set_workarea

# En la app compilada (PyInstaller) los recursos van a sys._MEIPASS; como script, junto al .py.
if getattr(sys, 'frozen', False):
    HERE = sys._MEIPASS
else:
    HERE = os.path.dirname(os.path.abspath(__file__))


def _load_workarea():
    """Área de trabajo guardada (misma config que la app vieja), o el default del plotter."""
    try:
        p = core._config_path()
        if p.exists():
            d = json.loads(p.read_text())
            return float(d.get('work_w', 3000.0)), float(d.get('work_h', 600.0))
    except Exception:
        pass
    return 3000.0, 600.0


class Api:
    """Métodos que la interfaz web puede llamar (window.pywebview.api.*)."""

    def __init__(self):
        self.window = None

    def get_workarea(self):
        ww, wh = _load_workarea()
        return {'work': [ww, wh]}

    def set_workarea(self, w, h):
        return _set_workarea(w, h)

    def open_design(self):
        """Abre un diálogo nativo. Acepta un diseño (SVG/DXF/AI) o un proyecto (.dstudio)."""
        res = self.window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False,
            file_types=('Diseños y proyectos (*.svg;*.dxf;*.ai;*.dstudio)', 'Todos los archivos (*.*)'))
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res[0] if isinstance(res, (list, tuple)) else res
        ext = os.path.splitext(path)[1].lower()
        if ext == '.dstudio':
            try:
                proj = json.loads(open(path, encoding='utf-8').read())
                return {'ok': True, 'kind': 'project', 'project': proj,
                        'name': os.path.basename(path)}
            except Exception as e:
                return {'ok': False, 'error': f'No se pudo abrir el proyecto: {e}'}
        try:
            if ext == '.svg':
                styled = core.SVGParser().parse(path)
            elif ext == '.dxf':
                styled = core.DXFParser().parse(path)
            elif ext == '.ai':
                styled = core.AIParser().parse(path)
            else:
                return {'ok': False, 'error': 'Formato no soportado (usa SVG, DXF, AI o .dstudio).'}
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo leer el archivo: {e}'}

        paths = []
        xs, ys = [], []
        for d in styled:
            pts = d.get('pts') or []
            if len(pts) < 2:
                continue
            rp = [[round(float(x), 3), round(float(y), 3)] for (x, y) in pts]
            paths.append({'pts': rp})
            for x, y in rp:
                xs.append(x); ys.append(y)
        bbox = [min(xs), min(ys), max(xs), max(ys)] if xs else [0, 0, 0, 0]
        ww, wh = _load_workarea()
        return {'ok': True, 'name': os.path.basename(path),
                'paths': paths, 'bbox': bbox, 'work': [ww, wh]}

    def _hpgl(self, data):
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

    def gen_hpgl(self, data):
        try:
            hpgl = self._hpgl(data)
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo generar el HPGL: {e}'}
        return {'ok': True, 'hpgl': hpgl, 'lines': hpgl.count('\n') + 1, 'bytes': len(hpgl)}

    def save_hpgl(self, data):
        try:
            hpgl = self._hpgl(data)
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        name = (data.get('name') or 'diseno').rsplit('.', 1)[0] + '.hpgl'
        res = self.window.create_file_dialog(webview.SAVE_DIALOG, save_filename=name)
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res if isinstance(res, str) else res[0]
        try:
            with open(path, 'w') as f:
                f.write(hpgl)
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo guardar: {e}'}
        return {'ok': True, 'path': os.path.basename(path)}

    def save_project(self, data):
        """Guarda el proyecto completo (trazados + transforms + área + corte) a un .dstudio."""
        name = (data.get('name') or 'proyecto')
        name = name.rsplit('.', 1)[0] + '.dstudio'
        res = self.window.create_file_dialog(webview.SAVE_DIALOG, save_filename=name)
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res if isinstance(res, str) else res[0]
        if not path.lower().endswith('.dstudio'):
            path += '.dstudio'
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo guardar: {e}'}
        return {'ok': True, 'path': os.path.basename(path)}

    # --- Plotter (Fase 3, SIN verificar con hardware) — delega en el servicio compartido ---
    def ports(self):            return SERVICE.ports()
    def plotter_status(self):   return SERVICE.status()
    def connect(self, port, baud=9600): return SERVICE.connect(port, baud)
    def disconnect(self):       return SERVICE.disconnect()
    def jog(self, direction, dist=1): return SERVICE.jog(direction, dist)
    def pen(self, down):        return SERVICE.pen(bool(down))
    def command(self, which):   return SERVICE.command(which)
    def send_design(self, data): return SERVICE.send_design(data)
    def send_progress(self):    return SERVICE.progress()
    def cancel(self):           return SERVICE.cancel()
    def test_cut(self):         return SERVICE.test_cut()


def main():
    api = Api()
    win = webview.create_window(
        'Design Studio', os.path.join(HERE, 'studio_ui.html'),
        js_api=api, width=1300, height=820, min_size=(1040, 660),
        background_color='#0E1013')
    api.window = win
    webview.start()


if __name__ == '__main__':
    main()
