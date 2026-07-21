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

## ⚠️ El CLAUDE.md tiene datos desactualizados — NO confiar a ciegas, verificar contra código
Documentación podrida detectada al dar de alta el proyecto (la trampa #4 de la skill `nuevo-proyecto`):
- Dice que `plotter_control.py` tiene **~2500 líneas** → **real: 3646**. La app creció y no se actualizó.
- Dice **"No hay panel izquierdo"** → pero el historial de git muestra commits *"Agregar panel de
  Capas con thumbnails"* y *"Mover controles a sidebar derecha"*. La UI cambió; el CLAUDE.md quedó atrás.

**Por qué importa:** el CLAUDE.md se lee cada sesión como si fuera verdad. Si describe una UI que ya
no existe, la IA razona sobre un programa fantasma. **Antes de tocar la UI o el layout, leer el
código real, no el CLAUDE.md.** Pendiente: auditar y reescribir el CLAUDE.md contra `plotter_control.py`
(hoy son 500 líneas de resumen de arquitectura, cuando la regla es <200 y solo lo no-derivable).

## Cómo correrlo (para desarrollo/lectura en Mac)
```bash
cd ~/plotter-antike && python plotter_control.py   # requiere Python 3.8+ con tkinter
```
Las dependencias (pyserial, svgpathtools, ezdxf, pymupdf) son **opcionales**: la app arranca sin
ellas y solo deshabilita la función correspondiente (flags HAS_SERIAL/HAS_SVG/HAS_DXF/HAS_MUPDF).
