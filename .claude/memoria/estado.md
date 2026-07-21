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

## Cómo correrlo en la Mac de Jose (instalado el 21-jul-2026)
⚠️ **Usar el Python de Homebrew, NO el del sistema:**
```bash
/opt/homebrew/bin/python3 /Users/josegf/plotter-antike/plotter_control.py   # Python 3.14, Tk 9.0
```
Hay un **ícono "Plotter Antike" en el Escritorio** (app de AppleScript) que lanza justo eso con
doble clic. Dependencias instaladas para ese Python: `pyserial ezdxf pymupdf`
(`... -m pip install --break-system-packages ...`). Las flags HAS_SERIAL/HAS_DXF/HAS_MUPDF gatean
funciones opcionales; HAS_SVG casi no importa (el parser SVG primario usa la stdlib).

### Por qué NO el Python del sistema (`/usr/bin/python3`) — la trampa que costó una sesión
El Python del sistema trae **Tk 8.5.9 (de 2010)**, que se **rompe con el Modo Oscuro de macOS**:
ignora los colores que el programa pide y pinta TODOS los fondos en negro → el contenido queda
invisible aunque el código pida gris claro (`_IBG = '#ebebeb'`). **La señal:** widgets con `bg`
claro explícito que salen oscuros = problema del motor Tk, no del código. **El arreglo definitivo**
fue `brew install python-tk@3.14` (trae Tk 9.0, que sí respeta los colores) y correr con ese Python.
Además se añadió al código un bloque `if sys.platform == 'darwin':` que fuerza tema `clam` + paleta
clara **solo en Mac** (en Windows/Linux el tema nativo se ve bien y no se toca).
