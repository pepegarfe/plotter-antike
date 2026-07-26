#!/usr/bin/env python3
"""
Auto-actualización de Design Studio desde GitHub Releases.

Flujo (tres pasos, para que la interfaz pueda mostrar avance):
  1. `check()`      — pregunta a GitHub cuál es el último release y compara versiones.
  2. `start(url)`   — descarga el .zip en un hilo; `status(job)` reporta el % de avance.
  3. `apply(job)`   — descomprime, deja un ayudante corriendo y CIERRA la app; el ayudante
                      espera a que el proceso muera, reemplaza la instalación y la relanza.

Por qué un ayudante externo: un programa no puede sobrescribirse a sí mismo mientras
corre (en Windows el .exe queda bloqueado; en Mac el .app se está ejecutando). El
ayudante es un script chiquito que vive en una carpeta temporal.

⚠️ Solo actúa en la app COMPILADA (`sys.frozen`). Corriendo desde el código fuente
`apply()` se niega a tocar nada — ahí se actualiza con `git pull`.
"""
import os
import re
import sys
import json
import tempfile
import zipfile
import subprocess
import threading
import urllib.request
from pathlib import Path

REPO = 'pepegarfe/plotter-antike'
APP = 'DesignStudio'
API_URL = f'https://api.github.com/repos/{REPO}/releases/latest'
PAGE_URL = f'https://github.com/{REPO}/releases/latest'
_UA = {'User-Agent': f'{APP}-updater', 'Accept': 'application/vnd.github+json'}

# Nombre del archivo del release que le toca a cada sistema.
_ASSET_HINT = {'win32': 'windows', 'darwin': 'mac'}


# ── versión propia ────────────────────────────────────────────────────────────

def _resource(name):
    """Ruta a un recurso empaquetado (igual que core._resource, sin importar tkinter)."""
    if getattr(sys, 'frozen', False):
        return Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent)) / name
    return Path(__file__).resolve().parent / name


def current_version():
    try:
        v = _resource('version.txt').read_text(encoding='utf-8').strip()
        return v or 'dev'
    except Exception:
        return 'dev'


def vkey(s):
    """Versión → tupla de números para poder COMPARARLAS de verdad.

    ⚠️ Comparar versiones como texto es un error clásico: '2026.7.9' > '2026.7.10'
    porque '9' > '1' como letra. Por eso se comparan los números uno a uno.
    """
    nums = re.findall(r'\d+', str(s or ''))
    return tuple(int(n) for n in nums[:4])


def is_newer(latest, current):
    """¿`latest` es posterior a `current`? En modo desarrollo ('dev') nunca."""
    a, b = vkey(latest), vkey(current)
    if not a or not b:          # 'dev' o basura → no molestar
        return False
    return a > b


def is_frozen():
    return bool(getattr(sys, 'frozen', False))


# ── paso 1: consultar GitHub ──────────────────────────────────────────────────

_ARCH_MARKS = ('arm64', 'applesilicon', 'aarch64', 'intel', 'x86_64')


def _pick_asset(assets):
    """El .zip que le toca a esta máquina: primero el sistema, luego el procesador.

    Lo del procesador es por si algún día el release trae dos paquetes de Mac (Apple
    Silicon e Intel): sin esto, cada máquina se bajaría el primero que apareciera."""
    hint = _ASSET_HINT.get(sys.platform)
    if not hint:
        return None
    cands = [a for a in assets or []
             if (a.get('name') or '').lower().endswith('.zip')
             and APP.lower() in (a.get('name') or '').lower()
             and hint in (a.get('name') or '').lower()]
    if not cands:
        return None
    import platform
    es_arm = platform.machine().lower() in ('arm64', 'aarch64')
    mios = ('arm64', 'applesilicon', 'aarch64') if es_arm else ('intel', 'x86_64')
    exacto = [a for a in cands if any(m in a['name'].lower() for m in mios)]
    if exacto:
        return exacto[0]
    # Sin paquete específico de mi procesador: el genérico (el que no marca ninguno).
    generico = [a for a in cands if not any(m in a['name'].lower() for m in _ARCH_MARKS)]
    return (generico or cands)[0]


def check(timeout=8):
    cur = current_version()
    out = {'ok': False, 'current': cur, 'dev': not is_frozen()}
    try:
        req = urllib.request.Request(API_URL, headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode('utf-8'))
    except Exception as e:
        out['error'] = f'No se pudo consultar GitHub ({e}). Revisa tu conexión.'
        return out
    latest = (data.get('tag_name') or '').strip().lstrip('vV')
    asset = _pick_asset(data.get('assets'))
    out.update({
        'ok': True,
        'latest': latest,
        'newer': is_newer(latest, cur),
        'name': (asset or {}).get('name'),
        'url': (asset or {}).get('browser_download_url'),
        'size': (asset or {}).get('size') or 0,
        'notes': (data.get('body') or '').strip()[:4000],
        'page': data.get('html_url') or PAGE_URL,
        'has_asset': bool(asset),
    })
    return out


# ── paso 2: descarga con avance ───────────────────────────────────────────────

_JOBS = {}
_SEQ = [0]


def _download(url, dest, job):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        total = int(r.headers.get('Content-Length') or 0)
        job['total'] = total
        got = 0
        with open(dest, 'wb') as f:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                job['got'] = got
                if total:
                    job['pct'] = min(99, int(got * 100 / total))
    if not dest.exists() or dest.stat().st_size < 1024:
        raise IOError('La descarga llegó vacía.')


def start(url=None):
    """Arranca la descarga en segundo plano. Devuelve el id del trabajo."""
    if not url:
        info = check()
        if not info.get('ok'):
            return info
        if not info.get('url'):
            return {'ok': False, 'error': 'Ese release no trae archivo para este sistema.'}
        url = info['url']
    _SEQ[0] += 1
    jid = str(_SEQ[0])
    tmp = Path(tempfile.mkdtemp(prefix='ds-update-'))
    job = {'pct': 0, 'got': 0, 'total': 0, 'done': False, 'error': None,
           'zip': tmp / 'update.zip', 'dir': tmp, 'stage': 'descargando'}
    _JOBS[jid] = job
    for k in list(_JOBS.keys())[:-3]:            # no acumular trabajos viejos
        _JOBS.pop(k, None)

    def work():
        try:
            _download(url, job['zip'], job)
            job['pct'] = 100
            job['stage'] = 'listo'
        except Exception as e:
            job['error'] = f'Falló la descarga: {e}'
            job['stage'] = 'error'
        job['done'] = True

    threading.Thread(target=work, daemon=True).start()
    return {'ok': True, 'job': jid}


def status(job_id):
    job = _JOBS.get(str(job_id or ''))
    if not job:
        return {'ok': False, 'error': 'Descarga desconocida.'}
    if job['error']:
        return {'ok': False, 'error': job['error']}
    return {'ok': True, 'pct': job['pct'], 'got': job['got'],
            'total': job['total'], 'done': job['done'], 'stage': job['stage']}


# ── paso 3: instalar y relanzar ───────────────────────────────────────────────

def app_root():
    """Lo que hay que reemplazar: el .app en Mac, la carpeta del .exe en Windows."""
    exe = Path(sys.executable).resolve()
    if sys.platform == 'darwin':
        for p in exe.parents:
            if p.suffix == '.app':
                return p
    return exe.parent


def _find_payload(root):
    """Dentro del zip descomprimido: el .app (Mac) o la carpeta con el .exe (Windows)."""
    if sys.platform == 'darwin':
        for p in sorted(root.rglob('*.app')):
            if (p / 'Contents' / 'MacOS').is_dir():
                return p
    else:
        for p in sorted(root.rglob(f'{APP}.exe')):
            return p.parent
    return None


def _apply_mac(payload, dest, helper_dir, payload_dir):
    """Ayudante bash: espera a que muera esta app, la reemplaza y la vuelve a abrir."""
    sh = helper_dir / 'aplicar.sh'
    sh.write_text(f'''#!/bin/bash
# Ayudante de actualización de {APP}. Se borra solo al terminar.
DEST="{dest}"
SRC="{payload}"
# Nunca tocar algo que no sea un .app válido.
case "$DEST" in *.app) ;; *) exit 1 ;; esac
[ -d "$DEST/Contents/MacOS" ] || exit 1
# Esperar a que la app muera. ⚠️ No sirve `kill -0`: un proceso ZOMBI (terminado pero
# aún no recogido por su padre) sigue "existiendo" y el ayudante esperaría para siempre.
# Se mira el ESTADO real: sin estado = se fue; estado Z = zombi = también se fue.
N=0
while [ $N -lt 400 ]; do
  ST=$(ps -o stat= -p {os.getpid()} 2>/dev/null | tr -d ' ')
  [ -z "$ST" ] && break
  case "$ST" in Z*) break ;; esac
  sleep 0.3
  N=$((N+1))
done
sleep 0.6
rm -rf "$DEST"
/usr/bin/ditto "$SRC" "$DEST" || exit 1
/usr/bin/xattr -cr "$DEST" 2>/dev/null
/usr/bin/open "$DEST"
rm -rf "{payload_dir}"
''', encoding='utf-8')
    sh.chmod(0o755)
    subprocess.Popen(['/bin/bash', str(sh)], start_new_session=True)


def _apply_win(payload, dest, helper_dir, payload_dir):
    """Ayudante PowerShell: espera, espeja la carpeta nueva sobre la vieja y relanza."""
    ps = helper_dir / 'aplicar.ps1'
    ps.write_text(f'''$ErrorActionPreference = 'SilentlyContinue'
# Ayudante de actualización de {APP}.
try {{ Wait-Process -Id {os.getpid()} -Timeout 120 }} catch {{ }}
Start-Sleep -Milliseconds 900
robocopy "{payload}" "{dest}" /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
Start-Process -FilePath "{dest}\\{APP}.exe"
Remove-Item -Recurse -Force "{payload_dir}"
''', encoding='utf-8')
    subprocess.Popen(
        ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
         '-File', str(ps)],
        creationflags=getattr(subprocess, 'DETACHED_PROCESS', 0)
        | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))


def apply(job_id):
    """Descomprime y lanza el ayudante. Si devuelve ok, la app DEBE cerrarse ya."""
    job = _JOBS.get(str(job_id or ''))
    if not job:
        return {'ok': False, 'error': 'Descarga desconocida.'}
    if not job['done'] or job['error']:
        return {'ok': False, 'error': job['error'] or 'La descarga no ha terminado.'}
    if not is_frozen():
        return {'ok': False, 'error': 'Estás corriendo Design Studio desde el código fuente; '
                                      'actualízalo con "git pull" en vez de instalar el paquete.'}
    try:
        out = job['dir'] / 'nuevo'
        out.mkdir(exist_ok=True)
        if sys.platform == 'darwin':
            # ⚠️ En Mac hay que usar `ditto`: el zipfile de Python PIERDE los enlaces
            # simbólicos y el permiso de ejecución, y el .app queda inservible.
            subprocess.run(['/usr/bin/ditto', '-x', '-k', str(job['zip']), str(out)],
                           check=True, capture_output=True)
        else:
            with zipfile.ZipFile(job['zip']) as z:
                z.extractall(out)
        payload = _find_payload(out)
        if not payload:
            return {'ok': False, 'error': 'El paquete descargado no trae la aplicación.'}
        dest = app_root()
        helper = Path(tempfile.mkdtemp(prefix='ds-apply-'))   # fuera de lo que se borra
        if sys.platform == 'darwin':
            _apply_mac(payload, dest, helper, job['dir'])
        elif sys.platform == 'win32':
            _apply_win(payload, dest, helper, job['dir'])
        else:
            return {'ok': False, 'error': 'La instalación automática solo existe en Windows y Mac.'}
        return {'ok': True, 'quit': True}
    except Exception as e:
        return {'ok': False, 'error': f'No se pudo instalar: {e}'}
