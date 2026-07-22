---
name: design-studio
description: Design Studio — la interfaz nueva (web/pywebview) que reconstruye Plotter Antike; estado y cómo correrla/compilarla
metadata:
  type: project
---

# Design Studio — la interfaz nueva (rebuild)

Construida el 21-jul-2026. Es un **programa nuevo** que reconstruye la cara de Plotter Antike con
aspecto pro, **reutilizando el motor** (`plotter_control.py`: parsers SVG/DXF/AI, `HPGLConverter`,
`PlotterController`). El original tkinter **sigue intacto** (Plotter Antike no se tocó).

## Por qué existe
El aspecto de la app tkinter tiene techo (no compite con Illustrator). Jose pidió reconstruir para un
look profesional. Se eligió **web + backend Python** (pywebview) porque la maqueta aprobada es HTML/CSS
y así se convierte directo en la app; el motor Python se reusa por debajo.

## Arquitectura y archivos (todos en `~/plotter-antike/`)
- **`design_studio.py`** — entrada de ESCRITORIO (ventana nativa pywebview). Clase `Api` = puente
  JS↔Python. Carga `studio_ui.html`.
- **`studio_server.py`** — modo SERVIDOR web (bottle, puerto 8765): sirve `studio_ui.html` y expone la
  misma API por HTTP. Es el modo con el que se DEPURA en Chrome. (La idea de usarlo multi-dispositivo
  está en pausa → [[idea-web-online]].)
- **`studio_ui.html`** — TODA la interfaz (HTML/CSS/JS). El motor de edición (transformaciones,
  selección, capas, historial) vive en **JavaScript**; solo parseo/HPGL/serial van a Python.
  ⚠️ Tiene un `window.__DS` de depuración (inofensivo).
- **`studio_backend.py`** — `PlotterService` (SERVICE) compartido: conexión serial, control manual,
  envío en hilo con progreso, cancelar; y `set_workarea`, `build_hpgl`.

## Estado (21-jul-2026)
- **Fase 1 (editar): ✅ verificada en vivo** — abrir, selección (individual/grupo/todos, por capas y
  clic), mover, escalar (W/H y %), rotar, espejo, centrar, restablecer, capas con miniaturas,
  deshacer/rehacer, copiar/pegar/borrar. Motor de transform en JS (offset+escala+rotación por trazado).
- **Fase 2 (salida): ✅ verificada** — generar HPGL (idéntico al motor original), guardar, overlay de
  corte, parámetros, estimación de tiempo.
- **Fase 3 (plotter): ⚑ construida, cableado verificado, SERIAL SIN PROBAR** — panel de conexión,
  control manual, enviar con progreso, cancelar, test. Falta enchufar el plotter para verificar de verdad.
- **Fase 4: ✅ config verificada + app de Mac compilada** — editar/guardar área de trabajo (persiste en
  `plotter_config.json`, compatible con el original). **`dist/DesignStudio.app` compila y arranca** (97 MB).
  Falta: empaquetar Windows y probar visualmente la ventana compilada.

## Cómo correrla y compilarla (Mac, Python de Homebrew)
```bash
# Escritorio (ventana nativa):
/opt/homebrew/bin/python3 ~/plotter-antike/design_studio.py
# Modo web (para depurar en el navegador): abre http://localhost:8765
/opt/homebrew/bin/python3 ~/plotter-antike/studio_server.py
# Compilar app de Mac:
cd ~/plotter-antike && /opt/homebrew/bin/python3 -m PyInstaller --windowed --noconfirm \
  --name DesignStudio --add-data "studio_ui.html:." --add-data "version.txt:." \
  --collect-all webview design_studio.py    # → dist/DesignStudio.app
```

## Lecciones (señales)
- **Bug del lienzo que "no funcionaba":** un bucle de retroalimentación inflaba el `<canvas>` (medía
  su propio tamaño para fijarse el tamaño → crecía sin parar). Arreglo: `#cv{width:100%;height:100%}`.
  Señal: el contenedor medía 1076×701 pero el canvas reportaba 2400×1200.
- **En modo "Todos", clic en una figura debe seleccionarla individual** (no mover todo): `activeContains`
  debe devolver `false` cuando no hay selección explícita.
- Depurar el lienzo en Chrome (sirviendo con `studio_server.py`) es MUCHO más rápido que a ciegas.

Relacionado: [[estado]] (la app vieja), [[idea-web-online]] (multi-dispositivo, en pausa).
