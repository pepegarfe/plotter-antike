---
name: design-studio
description: Design Studio — la interfaz nueva (web/pywebview) que reconstruye Plotter Antike; estado y cómo correrla/compilarla
metadata: 
  node_type: memory
  type: project
  originSessionId: 661c489b-f53b-4842-91af-46e807877393
  modified: 2026-07-24T05:11:07.947Z
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

## 22-jul-2026: fidelidad de CURVAS arreglada en el MOTOR (plotter_control.py — ambas apps)
Jose reportó curvas "cuadriculadas" en imports. Causa: los 4 muestreadores (Béziers SVG C/S/Q/T,
arco A, círculo/elipse a 72 lados FIJOS, Béziers del AI) troceaban con densidad FIJA por unidad
interna del archivo — un viewBox chico escalado quedaba facetado. **Solución (la de los
programas pro): aplanado ADAPTATIVO por tolerancia** — `_flat_cubic`/`_flat_quad` (De Casteljau
recursivo) y `_arc_steps` (sagita), con tolerancia **RELATIVA** (~0.015% del tamaño de la curva
→ a prueba de escalados posteriores) + **piso absoluto 0.01 mm** (vía escala de la matriz raíz)
+ **pasada final `_simplify_mm`** (Douglas-Peucker a 0.01 mm, en mm, a la salida de SVG/AI/DXF).
Números verificados: círculo Ø90 → desviación 0.0099 mm (antes 0.048); Bézier de logo viewBox-24
a 200 mm → 0.0075 mm; escalar ×5 conserva 0.02% del radio; rectas intactas.
**Gotchas que costaron**: (1) tolerancia relativa POR TRAMO explota en trazos de cientos de
mini-curvas (potrace: 25k puntos en un círculo) → por eso el piso + la simplificación en mm;
(2) potrace mete un `<g transform="scale(0.1)">` que el piso calculado solo con la matriz raíz
no ve → por eso la limpieza final se hace en MM REALES post-matriz, que atrapa todo.
⚠️ No volver a muestrear curvas con N fijo (ver CLAUDE.md).
**Ronda 2 (commit 0f53cd2)**: el DXF seguía cuadriculado — su tolerancia era fija en UNIDADES
DEL DIBUJO y la escala $INSUNITS→mm se aplica DESPUÉS: un DXF declarado en metros (×1000) o
pulgadas (×25.4) quedaba con desviación real de hasta 1mm. Fix: `parse()` calcula la escala
primero y fija `self._tol = 0.01mm/escala`. Verificado idéntico (0.0099mm) en m/in/mm.
**Si un DXF sigue facetado tras esto**: el ARCHIVO trae las curvas ya trozadas en polilíneas
por el programa que lo exportó (Illustrator suele hacerlo) — eso ya no lo arregla ninguna
tolerancia; la solución sería re-ajuste de arcos/Béziers sobre polilíneas (el "curve fitting"
de Vectric), no construido.
**Ronda 3 — calibración contra caso REAL (commits be75891 + e06f2f7, cierre del 22-jul)**:
Jose seguía viendo "exactamente lo mismo" tras relanzar. Diagnóstico con SU archivo
(`vaquero salchichon.dxf`, Drive Cantarito/CORTE METAL: 17 SPLINEs reales, $INSUNITS=5=cm):
(a) para archivos en CM el fix de escala no cambiaba nada (0.001 unidades-cm ya eran 0.01mm) —
por eso viejo≈nuevo; (b) el flujo real de Jose es importar 81×205mm → **escalar ×10 en la
app** → inspeccionar a **5924% de zoom**, y la tolerancia relativa de 0.015% daba ~0.3mm
post-escala = 17px de quiebre a ese zoom. **Calibración final medida contra la spline exacta:
relativa 0.001% (1e-5) + pisos 0.001mm reales + _simplify_mm 0.001** → 0.0019mm al importar,
0.019mm tras ×10 = **1.1px a 5924%** (invisible), 3186 pts en todo el archivo.
**Lecciones**: (1) calibrar tolerancias contra el CASO DE USO real (escala máxima × zoom de
inspección), no contra "se ve bien al 100%"; (2) "sigue exactamente igual" tras un fix = o el
proceso corre código viejo, o el fix no toca ese camino — DIAGNOSTICAR CON EL ARCHIVO DEL
USUARIO (mdfind lo encontró en su Drive) antes de otra vuelta de tuerca a ciegas; (3) re-abrir
la app no basta: un diseño YA CARGADO (o un .dstudio) conserva los puntos horneados — hay que
RE-IMPORTAR el archivo fuente.

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

## Épica en curso: reemplazar Illustrator (iniciada 24-jul-2026, pedida por Jose)
Jose quiere diseñar TODO dentro de Design Studio (hoy solo edita lo importado). Orden acordado:
1) formas básicas → 2) texto con fuentes → 3) soldar/booleanas + contorno-offset → 4) edición de
nodos (al final a propósito: los trazos viven aplanados en puntos; editar anclas estilo
Illustrator pedirá otra representación). V-carve sigue fuera.
- **1. Formas básicas — ✅ COMMIT 86765a0 (24-jul, Jose las probó y pidió el botón único).** 4 herramientas
  nuevas en el riel: Rectángulo (R), Elipse (E), Polígono/Estrella (P, con popover Lados/Estrella/
  Interior% arriba-izquierda del lienzo), Línea (L). Arrastre estilo Illustrator con
  previsualización punteada en acento; Shift = cuadrado/círculo/ángulos 45°/rotación a 15°;
  polígono se dibuja DESDE EL CENTRO y el ángulo del arrastre lo rota; Escape vuelve a Selección.
  Elipse con segmentos por sagita (~0.002 mm, 48–720) — sin N fijo burdo (lección del 22-jul).
  Se puede dibujar sobre la mesa VACÍA (el overlay tiene pointer-events:none; al crear la 1ª
  forma se asigna nombre 'nuevo-diseno' ASCII). Umbral anti-fantasma: arrastres <4 px de PANTALLA
  no crean nada (en mm engañaba: alejado, medio píxel ya era >1 mm). Bloqueado en paso CNC
  (cncLock). **Jose las probó y pidió el patrón Illustrator: UN solo botón de figuras**
  (`toolShape`, con triangulito de "hay más") que al clic activa la última usada Y despliega el
  flyout con las 4 (`shapeFly`/`flyRect…`); elegir una cambia el icono del botón; clic fuera o
  mousedown en el lienzo lo cierra; los atajos R/E/P/L siguen y marcan la opción. ⚠️ El clic de
  cada opción lleva stopPropagation (son HIJAS del botón: sin él, el clic rebota al padre y
  reabre el menú). Verificado con el arnés node de DOM falso (29 checks: bbox exacto,
  deshacer/rehacer, radios de estrella, snap 45°, uids únicos, flyout). Arnés en scratchpad de
  la sesión (`test_shapes.js`); al arnés le hicieron falta `lastChild`/`dataset` en los
  elementos falsos y disparar toolFit para que la vista esté lista antes de simular.

- **2. Texto con fuentes del sistema — ✅ COMMIT c5c34d4 (24-jul).**
  Módulo nuevo **`text_vector.py`** (fontTools 4.63, ya estaba instalada; dependencia OPCIONAL con
  `HAS_FONTS` como las demás): `list_fonts()` escanea las carpetas del sistema (413 en la Mac,
  4.7s la 1ª vez, caché después; filtra emoji/símbolos/ocultas exigiendo A-a en el cmap) y
  `text_paths()` vectoriza con `BasePen` (resuelve composites, off-curves implícitos y
  súper-Béziers solos) + De Casteljau adaptativo ~0.003mm + `core._simplify_mm`. **El tamaño es
  ALTURA DE MAYÚSCULAS en mm** (medida sobre la H real; como Aspire, no puntos tipográficos).
  Kerning de tabla `kern` (GPOS fuera a propósito); tracking en mm; multilínea con interlineado
  natural×factor y alineación izq/centro/der. Baseline en Y=0, Y-arriba (la convención de la UI —
  el texto NO pasa por el volteo de SVG). Api `fonts`/`text_make` + rutas `/api/fonts`/`/api/text`.
  UI: herramienta T en el riel (atajo T) → modal (frase multilínea, selector de fuente, alto mm,
  espaciado, interlineado %, alineación) → "Crear texto" lo pone AGRUPADO al centro de la vista;
  **doble clic encima lo reedita** (regenera conservando el CENTRO del bbox viejo). La receta vive
  en `textMeta[gid]` y viaja en snapshot/undo y en el **.dstudio v3**; reeditar tras escalar a
  mano regenera al tamaño de la receta (limitación consciente v1). Verificado: 14 checks Python
  (H de 20mm=20mm, hueco de la O, kerning AV<AA, .ttc, script), 23 checks de UI en node con
  backend fingido, y punta a punta por el servidor real. **Gotchas de la sesión:** (1) el atajo
  global de teclado solo ignoraba INPUT — un textarea nuevo habría disparado herramientas/Supr
  al escribir; ahora ignora INPUT|TEXTAREA|SELECT; (2) volvió a morder el **servidor viejo en
  8765** (los curl devolvían 404-HTML: matar el proceso, como ya documentaba esta nota).

- **3. Booleanas + contorno-offset — ✅ COMMIT c9d2434 (24-jul).**
  Módulo nuevo **`geo_ops.py`** (shapely opcional, mismas convenciones que cnc_gcode: unidad =
  anillos par-impar con symmetric_difference, la O conserva su hueco): `boolean_op`
  (union/difference/intersection entre unidades) y `offset_op` (unión de las unidades +
  `buffer` con quad_segs por sagita ~0.005mm). Api `geo_boolean`/`geo_offset` + rutas
  `/api/boolean`/`/api/offset`. UI: sección **Combinar** (Unir/Restar/Intersectar, habilitadas
  con 2+ unidades) y **Contorno** (Dist ± mm + Crear; Enter en el campo dispara) en Propiedades.
  Reglas: **Restar = la unidad con índice de dibujo MÁS BAJO menos las demás** (la de abajo,
  como Minus Front de Illustrator — geoUnits ordena por Math.min de índices); las booleanas
  REEMPLAZAN los anillos consumidos (los trazos abiertos de esas unidades sobreviven y se
  avisa cuántos quedaron fuera); el contorno se SUMA como grupo nuevo seleccionado sin tocar
  el original; un texto soldado pierde su receta textMeta (ya no es texto) SOLO si el grupo
  quedó sin trazos. Verificado: 14 checks Python (áreas exactas, par-impar, contorno envolvente
  de figuras separadas, offset negativo devorador = error claro, arco de esquina ±0.01mm) +
  16 checks de UI simulada + e2e por el servidor real. **Gotcha del arnés**: tras dibujar con
  una herramienta hay que Escape antes de hacer marco — si no, el "marco" dibuja otra figura
  (dos checks fallaron por eso; no era bug de la app).

- **4. Edición de nodos (anclas + manijas) — ✅ COMMIT e856837 (24-jul, Jose la probó). Con esto la ÉPICA v1 QUEDA COMPLETA (formas → texto → booleanas/contorno → nodos).** El reto: los trazos viven APLANADOS en puntitos. Solución pro (la de Vectric): módulo
  **`curve_fit.py`** (Schneider de Graphics Gems, puro Python, sin dependencias) **re-ajusta
  Béziers** sobre la polilínea al entrar — detección de esquinas >35°, tramos de 2 pts = rectas
  exactas con manijas CERO, re-parametrización de Newton; rect→4 anclas exactas, círculo de
  300 pts→12 anclas suaves fieles a 0.018mm, estrella conserva sus 10 picos. Api `fit_nodes` +
  ruta `/api/fit`. UI: herramienta **flecha hueca "Editar nodos" (A)** en el riel; clic en un
  trazado → anclas (cuadritos); arrastrar ancla/manija, Shift+clic multi-selección, **doble
  clic agrega nodo** (en recta sin manijas; en curva parte con De Casteljau), **Supr quita**
  (respeta mínimo 2/3), manijas de anclas SUAVES giran en espejo conservando el largo de la
  gemela (colinealidad <5° al cargar = suave). **Esc/Enter/V/clic-en-vacío HORNEA** de vuelta a
  puntitos (flatten adaptativo 0.005mm; transform reseteado patrón mirrorActive; `nedit.uid`
  referencia por uid por si el doc cambia). Sin cambios = sin tocar doc ni historial; el
  pushUndo va en el PRIMER arrastre real (Cmd+Z durante la edición = hornear y deshacer → el
  original). `__DS` ganó getter `nedit` para los arneses. Verificado: 13 checks Python del fit
  + 23 de UI simulada + e2e (14 anclas para círculo de 200 pts por el servidor real).
  ⚠️ Limitación consciente v1: no hay "sacar manijas" de una esquina recta (convertir recta en
  curva) — se suple insertando nodos en la curva vecina; retomar si Jose lo pide.

- **5. Rondas 1+2 de diseño (9 funciones) — ✅ COMMIT 7279562 (24-jul, Jose las probó).**
  Pedidas por Jose en bloque ("adelante con las dos rondas"). Qué entró:
  · **Texto en arco**: campo "Curva" (±grados) en el modal — cada glifo se coloca RÍGIDO sobre el
    círculo (rota, no se deforma; + = arco, − = valle; por línea, R = ancho/θ); viaja en la
    receta textMeta. ⚠️ El ancho total PUEDE crecer con el arco (las letras inclinadas
    sobresalen) — el invariante correcto es que la ALTURA crece.
  · **Pluma (P — le QUITÓ el atajo al polígono, que quedó solo en el flyout)**: clic=esquina,
    arrastre=ancla suave con manijas simétricas, clic en el 1º=cerrar, Esc/Enter=terminar,
    Cmd+Z quita el último punto; liga elástica curva al cursor; hornea con nodePts (la cocina
    del editor de nodos) vía `insertPath()` (helper nuevo que también usan formas y tijeras).
  · **Tijeras (C)**: clic sobre un trazado → abierto queda en DOS (mismo grupo, puntas
    coincidentes en el corte); cerrado se ABRE por ahí (arranca y termina en el corte).
    ⚠️ Limitación: el anillo abierto conserva puntas coincidentes → el criterio de cierre por
    distancia lo sigue viendo "cerrado"; un 2º corte re-abre en otro punto, no parte en dos.
  · **Imanes (snapping)**: al ARRASTRAR, bordes/centros de la selección se pegan (6 px) a
    bordes/centros de las demás unidades + hoja + guías; líneas de imán en acento; Alt lo
    apaga. El arrastre se REHIZO de incremental a delta-total (orig+delta) para que el imán no
    acumule deriva — moving ahora guarda A/orig/candidatos.
  · **Reglas y guías**: reglas en mm (22 px, paso adaptativo 1–1000 según zoom); arrastrar
    DESDE la regla crea guía (izq=vertical, arriba=horizontal), re-arrastrable, soltarla en la
    regla la borra, clic en la ESQUINA borra todas; van en el .dstudio (`guides`).
  · **Copias en círculo**: el modal Copias ganó segmentado Rejilla|Círculo (N, radio, ángulo);
    pivote a "radio" mm BAJO el centro de la selección, sentido horario, 360=n reparte /
    parcial=/(n−1) — coronas/relojes.
  · **Engrosar línea** (`expand_op`, LineString.buffer): abiertos → cápsula cerrada con grosor
    total; REEMPLAZA la línea. Botón en Contorno (activo solo con abiertos en la selección).
  · **Esquinas redondeadas** (`round_op`, apertura+cierre morfológicos −r/+2r/−r): redondea
    convexas Y cóncavas, por unidad (vecinas no se funden), figura devorada por el radio se
    devuelve INTACTA con aviso; REEMPLAZA. Botón en sección Esquinas.
  · **Imagen de referencia** (riel): foto tenue (40%) centrada a la hoja, bloqueada, debajo de
    todo; clic de nuevo la quita; solo de la SESIÓN (no viaja al .dstudio a propósito — base64
    inflaría el archivo). Escritorio: Api `ref_image` (data-URL); web: `refInput`+FileReader.
  Rutas nuevas `/api/expand` `/api/round` + Api geo_expand/geo_round/ref_image; `geoRemove()`
  (helper de borrado+poda de textMeta) y `GEO_API` (mapa de geoCall). __DS ganó pen/guides/
  refImg/snapGuides. ⚠️ Gotcha de arranque: las vars nuevas que draw() pinta (guides/RUL/
  refImg) deben declararse ANTES de draw() en el archivo — draw corre durante la carga.
  Verificado: 34 checks nuevos de UI + 18 de motores Python + regresión completa (125 checks
  UI en 5 arneses) + e2e real (expand/round/texto-arco). El arnés aprendió: E(id) crea el
  elemento falso al vuelo y `_segBtns` generaliza los segmentados.

## Novedades 23–24 jul 2026
- **`.ai` arreglado EN EL MOTOR (commit 492b1c8)**: los .ai perdían trazados enteros (18 de 39 en
  el logo de chalecos — todo path que empezara con curva se tragaba en silencio) y deformaban las
  curvas sobrevivientes. Causa: `AIParser._items_to_subpaths` asumía formato estilo SVG para los
  items de pymupdf; el formato REAL trae TODOS los puntos por segmento (`('c', inicio, c1, c2,
  fin)`) y NO existen items 'm'/'h'. **Señal para la próxima**: si la librería cruda ve más
  elementos que la app, el que pierde es nuestro código.
- **Vista 3D del corte** (fases R en [[cnc-richauto]]) y **auditoría del G-code** (ídem).
- **Botón "Importar" — ⚠️ SIN COMMIT, pendiente vistazo de Jose (24-jul)**: suma otro archivo
  (SVG/DXF/AI/.dstudio) a la mesa SIN reemplazar. `addDoc`/`addProject` en studio_ui.html +
  `import_design`/`_load_vector` en design_studio.py (refactor: open_design usa el mismo helper).
  Reglas: lo existente intacto (uids viejos NO cambian → las trayectorias CNC calculadas
  sobreviven), lo nuevo entra como grupo propio a la derecha (+10mm, alineado abajo) y queda
  seleccionado; deshacible; mesa vacía → importar=abrir; de un .dstudio entran objetos con sus
  transformaciones pero **sus trayectorias NO** (uids ajenos, se avisa); grupos re-mapeados.
  Imágenes solo por Abrir (el calco reemplaza).
- **Técnica de prueba nueva que funcionó muy bien**: ejecutar el `<script>` COMPLETO de
  studio_ui.html en node con un **DOM falso mínimo** (Proxy con getElementById/addEventListener
  de mentira + getComputedStyle) y manejar la app por el gancho `window.__DS` (se le añadió
  `add`/`addProject`). Así se probó el flujo real de importar (9 checks) sin abrir la app.
  El extractor por marcadores (`node --check` + eval de funciones puras) sigue sirviendo para
  el módulo 3D.

### Pendientes (act. 24-jul-2026 — commit db5f141 + push: Importar, husillo/marchas,
### presets, auditoría y limpieza de UI ya SUBIDOS)
1. **Rebaba en MDF 3mm** (primera prueba real): diagnóstico en curso — sospechosos: filo
   cansado (prueba A/B con la 1/8" pendiente), cama comida, mordida baja (preset ya subido
   a 4000) y fresa upcut. **Recomendación en pie: fresa DOWNCUT para lámina delgada** —
   al comprarla, alta en "Fresas…" con sus presets.
2. **Verificar orientación del corte en el plotter** — el arreglo del eje Y cambió el HPGL ([[estado]] Fase 3).
   Necesita hardware; nadie puede cerrarlo desde la Mac.
3. **Primer corte real de la CNC** — protocolo y checklist en [[cnc-richauto]] (auditoría ya pasada).
4. Diferidas que Jose puede querer: organizar orden (z-order / orden de corte), texto, contorno/offset,
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
