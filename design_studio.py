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
from studio_backend import (SERVICE, set_workarea as _set_workarea,
                            cnc_get as _cnc_get, cnc_set as _cnc_set, flip_paths_y,
                            cnc_toolpaths_preview as _cnc_preview, cnc_build_tap as _cnc_tap)
import img_trace as tracer
import text_vector as texter
import geo_ops as geo
import curve_fit as fitter

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


def _load_vector(path):
    """Lee un vector (SVG/DXF/AI) y lo entrega como lo espera la UI: trazados en mm
    con Y hacia ARRIBA (el volteo del SVG va aquí, POR FORMATO — ver flip_paths_y)."""
    ext = os.path.splitext(path)[1].lower()
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
    if ext == '.svg':
        flip_paths_y(paths)   # solo SVG viene Y-abajo; AI/DXF ya llegan Y-arriba
    ww, wh = _load_workarea()
    return {'ok': True, 'name': os.path.basename(path),
            'paths': paths, 'bbox': bbox, 'work': [ww, wh]}


class Api:
    """Métodos que la interfaz web puede llamar (window.pywebview.api.*)."""

    def __init__(self):
        self.window = None

    def get_workarea(self):
        ww, wh = _load_workarea()
        return {'work': [ww, wh]}

    def set_workarea(self, w, h):
        return _set_workarea(w, h)

    # --- CNC (Fase A): máquina activa, material y biblioteca de fresas ---
    def cnc_get(self):
        return _cnc_get()

    def cnc_set(self, patch):
        return _cnc_set(patch or {})

    def tools_export(self):
        """Guarda la biblioteca (materiales + fresas) como JSON con diálogo nativo."""
        cfg = _cnc_get()
        res = self.window.create_file_dialog(webview.SAVE_DIALOG,
                                             save_filename='fresas-antike.json')
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res if isinstance(res, str) else res[0]
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({'format': 'antike-tools', 'materials': cfg['materials'],
                           'tools': cfg['tools']}, f, ensure_ascii=False, indent=1)
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo guardar: {e}'}
        return {'ok': True, 'path': os.path.basename(path)}

    def tools_import(self):
        """Abre un JSON de biblioteca y REEMPLAZA materiales + fresas (validando)."""
        res = self.window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False,
            file_types=('Biblioteca de fresas (*.json)', 'Todos los archivos (*.*)'))
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res[0] if isinstance(res, (list, tuple)) else res
        try:
            d = json.loads(open(path, encoding='utf-8').read())
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo leer: {e}'}
        if not d.get('tools'):
            return {'ok': False, 'error': 'Ese archivo no trae fresas.'}
        return _cnc_set({'materials': d.get('materials'), 'tools': d['tools']})

    def cnc_toolpath(self, data):
        """Trayectorias del centro de la fresa, para previsualizar en el lienzo."""
        return _cnc_preview(data or {})

    def save_png(self, data):
        """Guarda una captura PNG de la Vista 3D (llega como data-URL base64)."""
        import base64
        d = data or {}
        try:
            raw = base64.b64decode((d.get('data') or '').split(',', 1)[1])
        except Exception:
            return {'ok': False, 'error': 'Captura vacía o corrupta.'}
        res = self.window.create_file_dialog(webview.SAVE_DIALOG,
                                             save_filename=d.get('name') or 'vista3d.png')
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res if isinstance(res, str) else res[0]
        if not path.lower().endswith('.png'):
            path += '.png'
        try:
            with open(path, 'wb') as f:
                f.write(raw)
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo guardar: {e}'}
        return {'ok': True, 'path': os.path.basename(path)}

    def cnc_tap_text(self, data):
        """El G-code como TEXTO (sin diálogo): lo consume la Vista 3D, que simula
        el corte comiéndose el mismo .tap que se llevaría la máquina."""
        return _cnc_tap(data or {})

    def save_tap(self, data):
        """Genera el G-code y lo guarda como .tap con diálogo nativo."""
        r = _cnc_tap(data or {})
        if not r.get('ok'):
            return r
        name = ((data or {}).get('name') or 'diseno').rsplit('.', 1)[0] + '.tap'
        res = self.window.create_file_dialog(webview.SAVE_DIALOG, save_filename=name)
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res if isinstance(res, str) else res[0]
        if not path.lower().endswith('.tap'):
            path += '.tap'
        try:
            with open(path, 'w', newline='\n') as f:
                f.write(r['tap'])
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo guardar: {e}'}
        return {'ok': True, 'path': os.path.basename(path),
                'lines': r['lines'], 'secs': r['secs'], 'skipped': r['skipped']}

    # --- Calco de imagen ---
    def trace_pick(self):
        res = self.window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False,
            file_types=('Imágenes (*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.webp)', 'Todos los archivos (*.*)'))
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res[0] if isinstance(res, (list, tuple)) else res
        return tracer.set_source(path)

    def trace_apply(self, options):
        return tracer.trace(options or {})

    # --- Texto con fuentes del sistema ---
    def fonts(self):
        return texter.list_fonts()

    def text_make(self, data):
        return texter.text_paths(data or {})

    # --- Booleanas y contorno (diseño) ---
    def geo_boolean(self, data):
        return geo.boolean_op(data or {})

    def geo_offset(self, data):
        return geo.offset_op(data or {})

    def fit_nodes(self, data):
        """Polilínea → anclas+manijas Bézier, para la edición de nodos."""
        return fitter.fit_nodes(data or {})

    def geo_expand(self, data):
        return geo.expand_op(data or {})

    def geo_round(self, data):
        return geo.round_op(data or {})

    def ref_image(self):
        """Imagen de referencia: diálogo nativo → data-URL para pintarla de fondo."""
        res = self.window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False,
            file_types=('Imágenes (*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.webp)', 'Todos los archivos (*.*)'))
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res[0] if isinstance(res, (list, tuple)) else res
        import base64
        import mimetypes
        mime = mimetypes.guess_type(path)[0] or 'image/png'
        try:
            data = base64.b64encode(open(path, 'rb').read()).decode()
        except Exception as e:
            return {'ok': False, 'error': f'No se pudo leer la imagen: {e}'}
        return {'ok': True, 'data': f'data:{mime};base64,{data}'}

    def open_design(self):
        """Abre un diálogo nativo. Acepta un diseño (SVG/DXF/AI), un proyecto (.dstudio)
        o una imagen (PNG/JPG…) que se manda directo al calco."""
        res = self.window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False,
            file_types=('Diseños imágenes y proyectos '
                        '(*.svg;*.dxf;*.ai;*.dstudio;*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.webp;*.tif;*.tiff)',
                        'Todos los archivos (*.*)'))
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res[0] if isinstance(res, (list, tuple)) else res
        ext = os.path.splitext(path)[1].lower()
        if ext in ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tif', '.tiff'):
            r = tracer.set_source(path)
            if isinstance(r, dict) and r.get('ok'):
                r['kind'] = 'image'
            return r
        if ext == '.dstudio':
            try:
                proj = json.loads(open(path, encoding='utf-8').read())
                return {'ok': True, 'kind': 'project', 'project': proj,
                        'name': os.path.basename(path)}
            except Exception as e:
                return {'ok': False, 'error': f'No se pudo abrir el proyecto: {e}'}
        return _load_vector(path)

    def import_design(self):
        """Como open_design pero para SUMAR a la mesa (no reemplaza): solo vectores
        y proyectos. Las imágenes van por Abrir — el calco siempre reemplaza."""
        res = self.window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False,
            file_types=('Diseños y proyectos (*.svg;*.dxf;*.ai;*.dstudio)',
                        'Todos los archivos (*.*)'))
        if not res:
            return {'ok': False, 'cancelled': True}
        path = res[0] if isinstance(res, (list, tuple)) else res
        if os.path.splitext(path)[1].lower() == '.dstudio':
            try:
                proj = json.loads(open(path, encoding='utf-8').read())
                return {'ok': True, 'kind': 'project', 'project': proj,
                        'name': os.path.basename(path)}
            except Exception as e:
                return {'ok': False, 'error': f'No se pudo abrir el proyecto: {e}'}
        return _load_vector(path)

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
    # Calentar el listado de fuentes en segundo plano: cuando el usuario abra el
    # modal de Texto ya está listo (con caché de disco es instantáneo; sin él,
    # el escaneo de ~5 s corre mientras la ventana arranca).
    import threading
    threading.Thread(target=texter.list_fonts, daemon=True).start()
    api = Api()
    win = webview.create_window(
        'Design Studio', os.path.join(HERE, 'studio_ui.html'),
        js_api=api, width=1300, height=820, min_size=(1040, 660),
        background_color='#0E1013')
    api.window = win
    webview.start()


if __name__ == '__main__':
    main()
