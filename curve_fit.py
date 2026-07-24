# -*- coding: utf-8 -*-
"""Re-ajuste de curvas Bézier sobre polilíneas (el "curve fitting" de los
programas pro), para la edición de NODOS de Design Studio.

Los trazos del programa viven aplanados en puntitos (mm). Para editarlos como
Illustrator hay que recuperar una descripción editable: anclas + manijas. Este
módulo la produce con el algoritmo clásico de Schneider (Graphics Gems, "An
Algorithm for Automatically Fitting Digitized Curves") + detección de esquinas:

    fit_nodes({'pts': [[x,y]...], 'closed': bool, 'tol': mm}) →
      {'ok': True, 'closed': bool,
       'nodes': [{'p':[x,y], 'hin':[x,y], 'hout':[x,y]}, ...]}

- 'hin'/'hout' son las manijas en coordenadas ABSOLUTAS; una manija que
  coincide con su ancla (longitud cero) = lado recto/esquina.
- Las esquinas (quiebres > _CORNER_DEG) se respetan como anclas duras; los
  tramos rectos de 2 puntos quedan como rectas exactas.
- La UI edita las anclas y al salir HORNEA la curva de vuelta a puntitos.

Sin dependencias (puro Python).
"""

import math

_CORNER_DEG = 35.0     # quiebre mayor a esto = esquina dura
_MAX_ITER = 5          # intentos de re-parametrización de Newton


# ------------------------------------------------------------------ vectores

def _sub(a, b): return (a[0] - b[0], a[1] - b[1])
def _add(a, b): return (a[0] + b[0], a[1] + b[1])
def _scale(a, s): return (a[0] * s, a[1] * s)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1]
def _len(a): return math.hypot(a[0], a[1])
def _dist2(a, b): return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _norm(a):
    L = _len(a)
    return (a[0] / L, a[1] / L) if L > 1e-12 else (0.0, 0.0)


def _bezier(b, t):
    """Punto de la cúbica b=(p0,c1,c2,p3) en t."""
    mt = 1 - t
    a0 = mt * mt * mt
    a1 = 3 * mt * mt * t
    a2 = 3 * mt * t * t
    a3 = t * t * t
    return (a0 * b[0][0] + a1 * b[1][0] + a2 * b[2][0] + a3 * b[3][0],
            a0 * b[0][1] + a1 * b[1][1] + a2 * b[2][1] + a3 * b[3][1])


# ------------------------------------------------------ Schneider (fit cúbico)

def _chord_param(pts):
    u = [0.0]
    for i in range(1, len(pts)):
        u.append(u[-1] + math.sqrt(_dist2(pts[i], pts[i - 1])))
    total = u[-1] or 1.0
    return [x / total for x in u]


def _generate(pts, u, t1, t2):
    """Mínimos cuadrados para las longitudes de las manijas (alpha1/alpha2)."""
    n = len(pts)
    first, last = pts[0], pts[-1]
    A = []
    for i in range(n):
        ui = u[i]
        b1 = 3 * ui * (1 - ui) ** 2
        b2 = 3 * ui * ui * (1 - ui)
        A.append((_scale(t1, b1), _scale(t2, b2)))
    C = [[0.0, 0.0], [0.0, 0.0]]
    X = [0.0, 0.0]
    for i in range(n):
        a0, a1 = A[i]
        C[0][0] += _dot(a0, a0)
        C[0][1] += _dot(a0, a1)
        C[1][1] += _dot(a1, a1)
        ui = u[i]
        mt = 1 - ui
        base = (first[0] * (mt ** 3 + 3 * ui * mt * mt) + last[0] * (3 * ui * ui * mt + ui ** 3),
                first[1] * (mt ** 3 + 3 * ui * mt * mt) + last[1] * (3 * ui * ui * mt + ui ** 3))
        tmp = _sub(pts[i], base)
        X[0] += _dot(a0, tmp)
        X[1] += _dot(a1, tmp)
    C[1][0] = C[0][1]
    det_C = C[0][0] * C[1][1] - C[1][0] * C[0][1]
    det_X0 = C[0][0] * X[1] - C[1][0] * X[0]
    det_X1 = X[0] * C[1][1] - X[1] * C[0][1]
    alpha1 = det_X1 / det_C if abs(det_C) > 1e-12 else 0.0
    alpha2 = det_X0 / det_C if abs(det_C) > 1e-12 else 0.0
    seg_len = math.sqrt(_dist2(first, last))
    eps = 1e-6 * seg_len
    if alpha1 < eps or alpha2 < eps:      # solución degenerada → heurística de Wu/Barsky
        alpha1 = alpha2 = seg_len / 3.0
    return (first, _add(first, _scale(t1, alpha1)), _add(last, _scale(t2, alpha2)), last)


def _max_error(pts, bez, u):
    max_e, split = 0.0, len(pts) // 2
    for i in range(1, len(pts) - 1):
        e = _dist2(_bezier(bez, u[i]), pts[i])
        if e > max_e:
            max_e, split = e, i
    return max_e, split


def _reparam(pts, u, bez):
    p0, c1, c2, p3 = bez
    # derivadas de la cúbica
    d1 = [_scale(_sub(c1, p0), 3), _scale(_sub(c2, c1), 3), _scale(_sub(p3, c2), 3)]
    d2 = [_scale(_sub(d1[1], d1[0]), 2), _scale(_sub(d1[2], d1[1]), 2)]
    out = []
    for i, ui in enumerate(u):
        q = _bezier(bez, ui)
        mt = 1 - ui
        q1 = (mt * mt * d1[0][0] + 2 * mt * ui * d1[1][0] + ui * ui * d1[2][0],
              mt * mt * d1[0][1] + 2 * mt * ui * d1[1][1] + ui * ui * d1[2][1])
        q2 = (mt * d2[0][0] + ui * d2[1][0], mt * d2[0][1] + ui * d2[1][1])
        diff = _sub(q, pts[i])
        den = _dot(q1, q1) + _dot(diff, q2)
        out.append(ui if abs(den) < 1e-12 else ui - _dot(diff, q1) / den)
    return out


def _fit_cubic(pts, t1, t2, err2):
    if len(pts) == 2:
        d = math.sqrt(_dist2(pts[0], pts[1])) / 3.0
        return [(pts[0], _add(pts[0], _scale(t1, d)), _add(pts[1], _scale(t2, d)), pts[1])]
    u = _chord_param(pts)
    bez = _generate(pts, u, t1, t2)
    max_e, split = _max_error(pts, bez, u)
    if max_e <= err2:
        return [bez]
    if max_e <= err2 * 16:
        for _ in range(_MAX_ITER):
            u = _reparam(pts, u, bez)
            bez = _generate(pts, u, t1, t2)
            max_e, split = _max_error(pts, bez, u)
            if max_e <= err2:
                return [bez]
    split = max(1, min(len(pts) - 2, split))
    tc = _norm(_sub(pts[split - 1], pts[split + 1]))       # tangente central (hacia atrás)
    left = _fit_cubic(pts[:split + 1], t1, tc, err2)
    right = _fit_cubic(pts[split:], _scale(tc, -1), t2, err2)
    return left + right


# --------------------------------------------------- esquinas y ensamblado

def _dedupe(pts):
    out = [tuple(pts[0])]
    for p in pts[1:]:
        if _dist2(tuple(p), out[-1]) > 1e-12:
            out.append(tuple(p))
    return out


def _turn_deg(prev, cur, nxt):
    v1, v2 = _norm(_sub(cur, prev)), _norm(_sub(nxt, cur))
    d = max(-1.0, min(1.0, _dot(v1, v2)))
    return math.degrees(math.acos(d))


def _corners(pts, closed):
    n = len(pts)
    out = []
    rng = range(n) if closed else range(1, n - 1)
    for i in rng:
        if _turn_deg(pts[i - 1], pts[i], pts[(i + 1) % n]) > _CORNER_DEG:
            out.append(i)
    return out


def fit_nodes(data):
    o = data or {}
    raw = o.get('pts') or []
    tol = float(o.get('tol') or 0.02)
    closed = bool(o.get('closed'))
    pts = _dedupe(raw)
    if closed and len(pts) > 2 and _dist2(pts[0], pts[-1]) <= 0.05 ** 2:
        pts = pts[:-1]
    n = len(pts)
    if n < 2 or (closed and n < 3):
        return {'ok': False, 'error': 'El trazado es demasiado corto para editar.'}

    corners = _corners(pts, closed)
    seam_suave = closed and not corners         # cortes ARTIFICIALES: la costura debe quedar lisa
    if closed:
        if not corners:
            corners = [0, n // 2]              # curva lisa: dos cortes artificiales
        r = corners[0]                          # rotar para arrancar en una esquina
        pts = pts[r:] + pts[:r]
        corners = [c - r for c in corners]
        runs, bordes = [], []
        cs = corners + [n]                      # el último tramo cierra al inicio
        ring = pts + [pts[0]]
        for k in range(len(corners)):
            runs.append(ring[cs[k]:cs[k + 1] + 1])
            bordes.append((cs[k] % n, cs[k + 1] % n))
    else:
        cs = [0] + corners + [n - 1]
        runs = [pts[cs[k]:cs[k + 1] + 1] for k in range(len(cs) - 1)]
        bordes = [None] * len(runs)

    err2 = tol * tol
    segs = []                                   # lista de cúbicas (p0,c1,c2,p3); recta = manijas en las puntas
    for ri, run in enumerate(runs):
        if len(run) < 2:
            continue
        if len(run) == 2:
            segs.append((run[0], run[0], run[1], run[1]))     # recta exacta
        else:
            if seam_suave and bordes[ri] is not None:
                # costura artificial: tangente CENTRAL (mirando ambos lados del corte)
                # para que el empalme no herede el quiebre de la faceta local
                i0, i1 = bordes[ri]
                t1 = _norm(_sub(pts[(i0 + 1) % n], pts[(i0 - 1) % n]))
                t2 = _norm(_sub(pts[(i1 - 1) % n], pts[(i1 + 1) % n]))
            else:
                t1 = _norm(_sub(run[1], run[0]))
                t2 = _norm(_sub(run[-2], run[-1]))
            segs.extend(_fit_cubic(run, t1, t2, err2))
    if not segs:
        return {'ok': False, 'error': 'No se pudo ajustar el trazado.'}

    nodes = []
    for k, s in enumerate(segs):
        prev = segs[k - 1] if (k > 0 or closed) else None
        nodes.append({'p': [s[0][0], s[0][1]],
                      'hin': [prev[2][0], prev[2][1]] if prev else [s[0][0], s[0][1]],
                      'hout': [s[1][0], s[1][1]]})
    if not closed:
        last = segs[-1]
        nodes.append({'p': [last[3][0], last[3][1]],
                      'hin': [last[2][0], last[2][1]],
                      'hout': [last[3][0], last[3][1]]})
    return {'ok': True, 'closed': closed, 'nodes': nodes}


def fit_nodes_many(data):
    """Lote de re-ajustes (para SUAVIZAR importaciones facetadas): cada item
    {pts, closed} se ajusta con la tolerancia dada (más alta que la de edición:
    debe TRAGARSE las facetas, no respetarlas) y devuelve sus nodos Bézier.
    La UI los hornea de vuelta a puntitos finos con nodePts."""
    o = data or {}
    tol = float(o.get('tol') or 0.1)
    out = []
    for it in o.get('items') or []:
        r = fit_nodes({'pts': it.get('pts'), 'closed': bool(it.get('closed')), 'tol': tol})
        out.append(r if r.get('ok') else {'ok': False})
    return {'ok': True, 'results': out}

