#!/usr/bin/env python3
"""
Design Studio — servidor web local.

Sirve la interfaz (studio_ui.html) por HTTP y expone el motor de corte como una pequeña API.
Corre en la computadora conectada al plotter; cualquier dispositivo en la misma red abre el
navegador en http://<ip-de-esta-mac>:8765 y usa Design Studio SIN instalar nada.

La lógica pesada (leer SVG/DXF/AI, HPGL, plotter) se reutiliza de plotter_control.py.
"""
import os
import json
import tempfile
import socket

from bottle import Bottle, static_file, request, response, HTTPResponse

import plotter_control as core
from studio_backend import (SERVICE, set_workarea as _set_workarea,
                            cnc_get as _cnc_get, cnc_set as _cnc_set,
                            flip_paths_y as _flip_paths_y,
                            cnc_toolpaths_preview as _cnc_preview, cnc_build_tap as _cnc_tap)
import img_trace as tracer

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8765
app = Bottle()


def _workarea():
    try:
        p = core._config_path()
        if p.exists():
            d = json.loads(p.read_text())
            return [float(d.get('work_w', 3000.0)), float(d.get('work_h', 600.0))]
    except Exception:
        pass
    return [3000.0, 600.0]


def _json(obj, status=200):
    return HTTPResponse(body=json.dumps(obj), status=status,
                        headers={'Content-Type': 'application/json; charset=utf-8'})


@app.get('/')
def index():
    return static_file('studio_ui.html', root=HERE)


@app.get('/api/workarea')
def api_workarea():
    return _json({'work': _workarea()})


@app.post('/api/set_workarea')
def api_set_workarea():
    d = request.json or {}
    return _json(_set_workarea(d.get('w'), d.get('h')))


@app.get('/api/cnc')
def api_cnc_get():
    return _json(_cnc_get())


@app.post('/api/cnc')
def api_cnc_set():
    return _json(_cnc_set(request.json or {}))


@app.post('/api/cnc_toolpath')
def api_cnc_toolpath():
    return _json(_cnc_preview(request.json or {}))


@app.post('/api/tap')
def api_tap():
    return _json(_cnc_tap(request.json or {}))


@app.post('/api/trace_upload')
def api_trace_upload():
    up = request.files.get('file')
    if up is None:
        return _json({'ok': False, 'error': 'No llegó ninguna imagen.'}, 400)
    ext = os.path.splitext(up.filename or 'img')[1].lower() or '.png'
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    tmp.close()
    up.save(tmp.name, overwrite=True)
    return _json(tracer.set_source(tmp.name))


@app.post('/api/trace')
def api_trace():
    return _json(tracer.trace(request.json or {}))


@app.post('/api/parse')
def api_parse():
    up = request.files.get('file')
    if up is None:
        return _json({'ok': False, 'error': 'No llegó ningún archivo.'}, 400)
    name = up.filename or 'archivo'
    ext = os.path.splitext(name)[1].lower()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    tmp.close()
    try:
        up.save(tmp.name, overwrite=True)
        if ext == '.svg':
            styled = core.SVGParser().parse(tmp.name)
        elif ext == '.dxf':
            styled = core.DXFParser().parse(tmp.name)
        elif ext == '.ai':
            styled = core.AIParser().parse(tmp.name)
        else:
            return _json({'ok': False, 'error': 'Formato no soportado (usa SVG, DXF o AI).'})
    except Exception as e:
        return _json({'ok': False, 'error': f'No se pudo leer el archivo: {e}'})
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    paths, xs, ys = [], [], []
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
        _flip_paths_y(paths)   # solo SVG viene Y-abajo; AI/DXF ya llegan Y-arriba
    return _json({'ok': True, 'name': name, 'paths': paths, 'bbox': bbox, 'work': _workarea()})


def _build_hpgl(data):
    """Genera HPGL a partir de los trazados efectivos (en mm) usando el motor del original."""
    paths = data.get('paths', [])
    conv = core.HPGLConverter(
        speed=int(float(data.get('speed', 320))),
        pressure=int(float(data.get('pressure', 140))),
        overcut_mm=float(data.get('overcut', 0.0)),
        corner_angle_deg=float(data.get('corner', 0.0)))
    conv.initialize()
    for p in paths:
        conv.add_path([(float(pt[0]), float(pt[1])) for pt in p])
    conv.finalize()
    return conv.get_hpgl()


@app.post('/api/hpgl')
def api_hpgl():
    try:
        data = request.json or {}
        hpgl = _build_hpgl(data)
    except Exception as e:
        return _json({'ok': False, 'error': f'No se pudo generar el HPGL: {e}'})
    return _json({'ok': True, 'hpgl': hpgl, 'lines': hpgl.count('\n') + 1, 'bytes': len(hpgl)})


# ── Plotter (Fase 3 — SIN verificar con hardware) ───────────────────────────────
@app.get('/api/ports')
def api_ports():
    return _json(SERVICE.ports())

@app.get('/api/status')
def api_status():
    return _json(SERVICE.status())

@app.post('/api/connect')
def api_connect():
    d = request.json or {}
    return _json(SERVICE.connect(d.get('port'), d.get('baud', 9600)))

@app.post('/api/disconnect')
def api_disconnect():
    return _json(SERVICE.disconnect())

@app.post('/api/jog')
def api_jog():
    d = request.json or {}
    return _json(SERVICE.jog(d.get('direction'), d.get('dist', 1)))

@app.post('/api/pen')
def api_pen():
    d = request.json or {}
    return _json(SERVICE.pen(bool(d.get('down'))))

@app.post('/api/command')
def api_command():
    d = request.json or {}
    return _json(SERVICE.command(d.get('which')))

@app.post('/api/send')
def api_send():
    return _json(SERVICE.send_design(request.json or {}))

@app.get('/api/send_progress')
def api_send_progress():
    return _json(SERVICE.progress())

@app.post('/api/cancel')
def api_cancel():
    return _json(SERVICE.cancel())

@app.post('/api/testcut')
def api_testcut():
    return _json(SERVICE.test_cut())


def _lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def main():
    ip = _lan_ip()
    print(f"Design Studio en:")
    print(f"  · esta Mac:        http://localhost:{PORT}")
    print(f"  · otros dispositivos (misma red): http://{ip}:{PORT}")
    from bottle import run
    run(app, host='0.0.0.0', port=PORT, quiet=True)


if __name__ == '__main__':
    main()
