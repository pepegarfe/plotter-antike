---
name: estado
description: 👉 LEER PRIMERO — qué es Plotter Antike, en qué estado quedó, y los avisos vivos
metadata:
  type: project
---

# Plotter Antike — estado

App de **escritorio Python/tkinter** que controla un **plotter de corte** por puerto COM/USB. Abre
un vector (SVG, DXF, AI), lo previsualiza, deja ajustar posición/escala/rotación y lo envía al
plotter en **HPGL**. Todo el código vive en un único archivo monolítico `plotter_control.py`.

Se **distribuye como .exe de Windows** (PyInstaller): `build.bat` compila, el usuario final corre
`instalar.bat` y queda en `%LOCALAPPDATA%\Antike\PlotterController\`. En Mac solo se desarrolla/lee;
no se puede probar el envío real al plotter aquí (no hay hardware ni el puerto COM).

## Estado al 21-jul-2026 (recién dado de alta en el sistema de conocimiento)
- Repo `pepegarfe/plotter-antike` (público), rama `master`, 25 commits, último hace ~8 semanas.
- Clonado en `~/plotter-antike`. **No es un proyecto activo** ahora mismo; se rescató del olvido.
- **No autodespliega** (es app de escritorio) → editar notas NO reinicia nada; sin candados de
  Watch Paths que cuidar, a diferencia de Omniseller.

## CLAUDE.md auditado y reescrito el 21-jul-2026 (ya es de fiar)
El CLAUDE.md original (500 líneas) describía una versión VIEJA del programa. Se verificó línea por
línea contra el código y se reescribió corto (~150 líneas, solo invariantes). Lo que estaba podrido
y se corrigió:
- Decía **`smooth=True`** en los canvas → hoy es **`smooth=False`** (se quitó a propósito para
  arreglar la fidelidad del corte). La regla vieja decía justo lo contrario de lo correcto.
- Describía la función **`_pinch_corners`** y la caché **`_pinched`** como vivas → son **código
  muerto**, nadie las llama.
- Describía la clase **`CutCanvas`** y una ventana aparte para los vectores de corte → **eliminadas**;
  hoy el corte es un overlay dentro de `DesignCanvas`.
- Decía **"no hay panel izquierdo"** y un Notebook de 3 pestañas arriba → la UI real es **barra de
  iconos a la izquierda + sidebar derecha** con pestañas "Props"/"Capas" y miniaturas de capas;
  "Plotter" y "Log COM" son **ventanas aparte**.
- No mencionaba features que SÍ existen: **espejo** (`_apply_mirror` H/V), **copiar/pegar**
  (Ctrl+C/V), **auto-actualización** desde GitHub, **forzar esquinas** (`corner_angle`).

**Lección (la señal que lo delató):** el historial de git mencionaba features que el CLAUDE.md
negaba. Cuando `git log` contradice al doc, el doc está viejo. Reorganizar no es verificar: hubo que
leer el código real, no copiar frases del doc anterior.

## Cómo correrlo (para desarrollo/lectura en Mac)
```bash
cd ~/plotter-antike && python plotter_control.py   # requiere Python 3.8+ con tkinter
```
Las dependencias (pyserial, svgpathtools, ezdxf, pymupdf) son **opcionales**: la app arranca sin
ellas y solo deshabilita la función correspondiente (flags HAS_SERIAL/HAS_SVG/HAS_DXF/HAS_MUPDF).
