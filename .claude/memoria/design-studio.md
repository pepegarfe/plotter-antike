---
name: design-studio
description: Design Studio — la interfaz nueva (web/pywebview) que reconstruye Plotter Antike; estado y cómo correrla/compilarla
metadata: 
  node_type: memory
  type: project
  originSessionId: 661c489b-f53b-4842-91af-46e807877393
  modified: 2026-07-23T00:49:25.758Z
---

# Design Studio — la interfaz nueva (rebuild)

Construida el 21-jul-2026. Es un **programa nuevo** que reconstruye la cara de Plotter Antike con
aspecto pro, **reutilizando el motor** (`plotter_control.py`: parsers SVG/DXF/AI, `HPGLConverter`,
`PlotterController`). El original tkinter **sigue intacto** (Plotter Antike no se tocó).

> **Es la cara NUEVA del mismo plotter.** La cara vieja (app tkinter) está en [[estado]]. Ambas
> comparten `plotter_control.py` y por eso viven en **un solo repo**: Design Studio lo importa;
> separarlos obligaría a duplicar el motor y arreglar cada bug dos veces.

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

## 22-jul-2026: Design Studio ahora también es el CAM de la CNC
Toda la épica CNC (fases A–H: pestañas Diseño|CNC, trayectorias estilo Aspire, fresas por
material, G-code .tap) vive en [[cnc-richauto]] — leer ESA nota antes de tocar nada del CNC.
Cambios de UI GENERAL que vinieron con ella (aplican a toda la app): **tema claro por default
y persistente** (clave `theme` en cnc_config.json), toggle de tema al final del riel izquierdo,
botón de área de trabajo junto al zoom (píldora propia, contenedor flex), iconos 100% SVG
(cero emojis/glifos), atajos Cmd+G/Cmd+Shift+G por `e.code`.

## Novedades sesión 21–22 jul 2026 (LEER al retomar)
Todo verificado en vivo (Chrome, modo web) y relanzado en escritorio. **Commit `f02e918` (pusheado)**:
- **Calco de imagen** (B/N + color) — ver sección "Calco de imagen" abajo.
- **"Abrir" acepta imágenes** (PNG/JPG/…): las manda directo al calco (además de SVG/DXF/AI y .dstudio).
  Arreglado el filtro de pywebview: **su validador NO admite comas** en la descripción del `file_type`.
- **Arreglo del eje Y** — ver sección "Eje Y" abajo. ⚠️ Falta verificar el corte en hardware.
- **Capas estilo Illustrator**: grupos como nodos plegables con hijos anidados (`buildLayers`/`layerRow`/
  `groupHeader` en studio_ui.html; estado de plegado en `layerCollapsed`).
- **Selección múltiple**: Shift / Cmd / Ctrl + clic suma/quita; Shift+arrastre = marco aditivo
  (`mousedown`/`mouseup` del lienzo; respeta grupos como unidad).

**Commit `73229b8`** (ya pusheado):
- **Alinear-a**: el `<select>` de texto "Selección/Área de trabajo" ahora es un **segmentado con iconos**
  (id `alignTo`, dos `<button data-to>`; estilo `.seg`). De regalo mejoró el resaltado del modo B/N/Color.

### Pendientes al 22-jul-2026 (árbol limpio, todo pusheado)
1. **Verificar orientación del corte en el plotter** — el arreglo del eje Y cambió el HPGL ([[estado]] Fase 3).
   Necesita hardware; nadie puede cerrarlo desde la Mac.
2. Diferidas que Jose puede querer: organizar orden (z-order / orden de corte), texto, contorno/offset,
   presets de material, optimizar orden de corte, snapping.

## Lanzador de escritorio (Mac) — ícono "Design Studio.app"
Igual que Plotter Antike, hay un **ícono en el Escritorio** que lanza la app con doble clic. Es una
**mini-app de AppleScript** (`osacompile`) que por dentro solo corre:
`/opt/homebrew/bin/python3 /Users/josegf/plotter-antike/design_studio.py`. **NO es la app compilada de
97 MB** (`dist/DesignStudio.app`); es el atajo ligero de desarrollo — si mueves/borras la carpeta del
código, deja de funcionar. Ícono propio: cuadro magenta de la marca + cursor blanco de selección.
- ⚠️ **Gotcha que costó rato:** en macOS moderno (26.x) reemplazar `Contents/Resources/applet.icns`
  **NO cambia el ícono** si la app trae un **`Assets.car`** (catálogo compilado) referenciado por
  `CFBundleIconName` en el `Info.plist` — **ese catálogo manda sobre el .icns**. Arreglo: `plutil -remove
  CFBundleIconName`, borrar `Assets.car`, `xattr -cr` (quitar detritus de Finder) y **re-firmar**
  (`codesign --force --deep -s -`); luego reventar caché (borrar `com.apple.iconservices*` de
  `$(getconf DARWIN_USER_CACHE_DIR)` + `killall Finder Dock`). **Señal:** cambiaste el .icns y Finder no
  lo refleja → busca un `Assets.car`.

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

## Calco de imagen (Image Trace) — `img_trace.py`
Convierte fotos (PNG/JPG…) en trazos de corte. Dos modos:
- **B/N (silueta):** Pillow (gris + umbral) → **potrace** (CLI, `brew install potrace`) → SVG con curvas
  Bézier suaves → `core.SVGParser` → trazos. Máxima fidelidad de contorno (familia del calco de Illustrator).
- **Color:** **vtracer** separa por colores. ⚠️ **El binding Python de vtracer 0.6.15 CRASHEA (segfault)
  si se le pasa CUALQUIER parámetro** — solo funciona con defaults. Solución: controlar la cantidad de
  colores **reduciéndolos antes con `Image.quantize`** y llamar a vtracer sin argumentos.
- **Dependencias** (para el Python de Homebrew): `potrace` (Homebrew) + `Pillow` + `vtracer` (pip
  `--break-system-packages`; hay wheel cp314). El módulo se llama **`img_trace.py`** (NO `trace.py`,
  que choca con la stdlib).
- **UI:** herramienta en el riel (icono de foto) → sube imagen → modal con Umbral/Suavizado/Ignorar
  manchas/Invertir (B/N) o Colores (color) → "Calcar" carga el resultado como diseño (agrupado).
- **La fidelidad la limita la imagen de entrada:** nítida y de alto contraste = buen calco.

## Conectar el plotter: Mac vs Windows (para probar la Fase 3)
El motor usa `pyserial` → `serial.tools.list_ports.comports()`, que nombra el puerto distinto según el
sistema. Es el MISMO dispositivo, distinto nombre:
- **Windows:** `COM3`, `COM4`, … (el usuario elige el COM).
- **Mac:** un archivo `/dev/cu.*`. El plotter aparece como **`/dev/cu.usbserial-…`** o
  **`/dev/cu.usbmodem…`** (o con el nombre del chip: `SLAB_USBtoUART`, `wchusbserial`). Se usa `cu.`
  (callout), no `tty.`. El panel de Design Studio ya lista estos nombres automáticamente.

**Cómo identificar el puerto del plotter en Mac:** con el plotter desconectado solo salen puertos
internos (`/dev/cu.debug-console`, `Bluetooth`, `Buds3…` — ninguno es el plotter). Se enchufa el
plotter, se pulsa ↻, y **el nombre nuevo que aparece es el plotter**. Baud casi siempre **9600**.

**Dos causas de "no aparece":**
1. **Plotters viejos usan RS-232 (serial DB-9), no USB.** Necesitan un **adaptador USB-a-Serial**; ese
   adaptador es el que se ve como `/dev/cu.usbserial-*`. Sin él no hay conexión con una Mac moderna.
2. **Falta el driver del chip** (CH340 / CP210x / Prolific): si al enchufar y refrescar la lista NO
   cambia, es esto — hay que instalar el driver del chip del cable.

## Eje Y — historia en DOS actos (¡leer los dos!)
**Acto 1 (21-jul):** los calcos y SVG salían boca abajo → se puso un **volteo ciego de TODOS los
imports** en `loadDoc` (JS).
**Acto 2 (22-jul): ese volteo ciego era un BUG.** Jose reportó que los diseños se volteaban "cuando
antes no". Verificado con pruebas (triángulo asimétrico por formato): **cada parser entrega una
orientación DISTINTA** —
- **SVG** (`core.SVGParser`, `_root_mtx` sin Y negativa): entrega **Y-abajo** → SÍ hay que voltear.
- **AI** (`core.AIParser`): **ya invierte la Y** al parsear (`page_h` en plotter_control) → NO tocar.
- **DXF**: Y-arriba de nacimiento → NO tocar.
- **Calcos** (potrace/vtracer): producen SVG → SÍ voltear.

**Arreglo definitivo:** el volteo vive en el **backend, por formato** — `flip_paths_y()` en
`studio_backend.py`, aplicado solo a `.svg` en `design_studio.open_design` y `studio_server
/api/parse`, y siempre en `img_trace._svg_to_paths`. El JS **no voltea nada** (`loadDoc` tiene el
comentario). **Convención firme: todo lo que llega a la UI ya viene Y-arriba.** El volteo es sobre
el centro del conjunto → el bbox no cambia.
- ⚠️ Sigue **pendiente verificar la orientación del corte en hardware** (plotter y, cuando llegue
  la Fase B del CNC, también el .tap).
- **Lección:** "todos los imports salen mal" era en realidad "solo los SVG salen mal". Antes de
  corregir una orientación global, **probar CADA formato con una forma asimétrica** (un triángulo
  punta-arriba delata el volteo al instante).

## Bugs arreglados 22-jul-2026 (reportados por Jose tras la Fase A del CNC)
1. **Calco: "No such file or directory: potrace"** — se invocaba `potrace` a secas y las apps
   lanzadas desde Finder (ícono del Escritorio) o entornos recortados **no tienen /opt/homebrew/bin
   en el PATH**. Arreglo: `_potrace_bin()` en img_trace.py resuelve ruta absoluta (which + rutas
   Homebrew típicas). **Señal:** "funciona en terminal pero no desde el ícono" = problema de PATH.
2. **Eje Y** (ver arriba, Acto 2).
3. **En modo CNC, abrir un diseño pisaba el área con la del plotter** — `open_design`/`/api/parse`
   devuelven el área del plotter y `loadDoc` la aplicaba sin mirar la máquina activa. Arreglo:
   guardia `if(state.machine==='plotter')` en `loadDoc` y `loadProject`.

## Lecciones (señales)
- **Bug del lienzo que "no funcionaba":** un bucle de retroalimentación inflaba el `<canvas>` (medía
  su propio tamaño para fijarse el tamaño → crecía sin parar). Arreglo: `#cv{width:100%;height:100%}`.
  Señal: el contenedor medía 1076×701 pero el canvas reportaba 2400×1200.
- **En modo "Todos", clic en una figura debe seleccionarla individual** (no mover todo): `activeContains`
  debe devolver `false` cuando no hay selección explícita.
- Depurar el lienzo en Chrome (sirviendo con `studio_server.py`) es MUCHO más rápido que a ciegas.

Relacionado: [[estado]] (la app vieja), [[idea-web-online]] (multi-dispositivo, en pausa).
