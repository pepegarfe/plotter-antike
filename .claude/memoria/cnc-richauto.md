---
name: cnc-richauto
description: "CNC router 122×244cm (Asia Robotics, controlador RichAuto DSP) — investigación del dialecto G-code y plan para integrarla a Design Studio estilo Vectric Aspire"
metadata: 
  node_type: memory
  type: project
  originSessionId: 661c489b-f53b-4842-91af-46e807877393
  modified: 2026-07-22T18:08:57.171Z
---

# CNC RichAuto — integración a Design Studio (planeada 22-jul-2026)

Jose tiene, además del plotter de corte, una **máquina CNC de 122×244 cm** (cama 1220×2440 mm)
comprada a **Asia Robotics**, con **controlador RichAuto DSP** (familia A1X — A11/A11E o similar,
el modelo exacto está por confirmar mirando el handle). Antes la trabajaba con **Vectric Aspire**;
quiere que Design Studio genere los **archivos G-code** con un flujo lo más parecido a Aspire.

## Investigación verificada (manual oficial RichAuto A1X, leído completo el 22-jul-2026)

**Cómo se trabaja:** el RichAuto es un controlador *offline* — NO se le manda el trabajo por cable
desde la compu. Se guarda el archivo G-code en una **USB (FAT16/32, recomiendan 2–8 GB)**, se
enchufa al handle y se procesa desde ahí. También se puede copiar al almacenamiento interno.
⚠️ El manual advierte: caracteres ilegales o G-code no estándar → error de lectura. Nombres de
archivo cortos y ASCII.

**Formatos que lee:** G-code (`.nc`, `.tap`, `.txt`, `.g`, `.u00`, `.mmg`), PLT, DXF, bitmap.
Usaremos **`.tap`** — lo pidió Jose explícitamente (22-jul-2026): es lo que su flujo con Aspire
producía (los posts de Vectric para RichAuto salen como `*.tap`). El contenido es G-code normal;
solo cambia la extensión.

**G-code soportado (lista oficial del manual, apéndice 9.4):** G00/G01/G02/G03, G04, G17-19,
G20/**G21**, G40-44/G49, **G54**-59, ciclos de taladrado G73/G81/G82/G83, **G90**/G91,
**M03/M04/M05**, M06, M08/M09, **M30**, y palabras T/S/F/H.

**⚠️ Trampas del controlador (menú "G Code Setup" del handle):**
- **`F Read` viene en "Ign F" de fábrica** → el controlador IGNORA las velocidades del archivo y
  usa su propia "Work Speed". Para que respete nuestras F hay que ponerlo en "Read F". Lo mismo
  con `S Read` (velocidad de husillo). **Documentar esto en la UI** — es la 1ª causa de "la
  máquina no hace caso a la velocidad que puse".
- `AbsCntr Off/On`: centros de arco (I,J) incrementales por defecto. **Nos da igual**: no vamos a
  emitir arcos (ver decisión abajo).
- En muchas máquinas chinas el husillo se controla con la **perilla del variador (VFD)**, no con
  la S del G-code — confirmar cómo está la de Jose.

**Decisión técnica clave — solo G00/G01, sin arcos:** el motor de Design Studio ya representa TODO
como polilíneas densamente muestreadas (styled paths = listas de puntos en mm). Emitir únicamente
movimientos lineales G01 es lo natural, elimina de raíz los problemas de arcos G02/G03 que
reportan los foros de Vectric con estos DSP, y el manual mismo usa ese estilo en sus ejemplos.

**Esqueleto de archivo seguro (calcado del ejemplo del manual):**
```
G90 G54          (absoluto, sistema de coordenadas 1)
G21              (milímetros)
M03 S18000       (husillo ON)
G00 Z<seguro>    (subir a altura segura)
G00 X.. Y..      (viajar)
G01 Z-<pasada> F<bajada>   (hundir)
G01 X.. Y.. F<corte>       (cortar)
...
G00 Z<seguro>
M05
M30
```

## Qué se imita de Aspire (el flujo que Jose ya conoce)
1. **Job Setup**: tamaño del material, **grosor**, cero de Z (cara superior o cama), datum XY.
2. **Biblioteca de herramientas**: fresa con diámetro, profundidad por pasada, stepover, RPM,
   avance de corte y de penetración (persistir en JSON junto a `plotter_config.json`).
3. **Trayectorias (toolpaths)**: Perfil (por fuera / por dentro / sobre la línea, con pasadas
   múltiples y puentes/tabs), Vaciado (pocket), Taladrado, y quizá V-carve (mucho más complejo).
4. **Preview de trayectorias + tiempo estimado**, lista de trayectorias, guardar `.nc`.

## Matemática nueva necesaria
- **Offset de polígonos** (perfil por fuera/dentro, vaciado por anillos): **`shapely` 2.1.2**
  (hay wheel cp314 arm64 para el Python de Homebrew — verificado con pip --dry-run el 22-jul).
- Z entra al juego por primera vez (el plotter era 2D): pasadas múltiples, altura segura, rampa.

## Plan por fases
- **A. Cimientos — ✅ CONSTRUIDA 22-jul-2026** (backend y API verificados con pruebas; falta el
  vistazo visual de Jose). Qué se hizo:
  - **`cnc_config.json`** (junto a `plotter_config.json`, vía `_cnc_path()` en `studio_backend.py`).
    ⚠️ **Archivo APARTE a propósito**: `_save_config()` de la app tkinter sobrescribe
    `plotter_config.json` con solo sus 6 llaves y habría borrado lo del CNC en silencio.
  - `cnc_get()`/`cnc_set()` en `studio_backend.py` (defaults + merge parcial + validación),
    expuestos en `design_studio.py` (Api) y `studio_server.py` (`GET/POST /api/cnc`).
  - **UI** (`studio_ui.html`): segmentado **Plotter | CNC** en la barra superior (persiste la
    elección); en modo CNC se ocultan "Exportar HPGL", "Enviar al plotter" y la píldora de
    conexión (la CNC es offline); aparece sección **Material** (grosor + cero de Z arriba/cama +
    Ø de la fresa activa) y **Herramienta** (selector + resumen + modal "Gestionar fresas…" con
    alta/baja/edición). El área de trabajo del modal de Configuración edita la máquina activa.
    Tiempo estimado en modo CNC usa el avance de la fresa (mm/min), no la velocidad del plotter.
  - 5 fresas preset (MDF, acrílico, PVC espumado, madera, 1/8" detalle) como punto de partida.
  - **Gotcha de la sesión:** un `studio_server.py` viejo seguía corriendo de la sesión anterior
    (puerto 8765 ocupado) — servía el HTML nuevo pero sin las rutas nuevas (404). **Señal:** el
    HTML trae los cambios pero la API no existe → proceso viejo; `lsof -iTCP:8765` y matarlo.
- **B. Perfil + G-code — ✅ CONSTRUIDA 22-jul-2026** (motor verificado con 6 pruebas unitarias +
  punta a punta por el servidor; falta vistazo visual de Jose y el corte real). Qué se hizo:
  - **`cnc_gcode.py`** (módulo nuevo): `make_toolpaths()` compensa la fresa con **shapely**
    (instalada 2.1.2). **Anidado par-impar** con `symmetric_difference` + `buffer(±r)`: la letra
    "O" por fuera expande el contorno Y contrae el hueco, como Aspire (verificado). Trazos
    abiertos: solo "Sobre la línea"; en fuera/dentro se saltan y se avisa cuántos.
    `build_gcode()` emite solo G00/G01, pasadas múltiples (techo de prof/pasada, la última exacta),
    cero de Z 'top' o 'bed' (verificadas ambas escalas de Z), altura segura +5mm, `M03 S`,
    `M05 / G00 X0 Y0 / M30`. **Comentarios normalizados a ASCII** (el manual advierte que
    caracteres raros rompen la lectura del controlador).
  - Backend: `cnc_toolpaths_preview()` / `cnc_build_tap()` en studio_backend; Api de escritorio
    `cnc_toolpath`/`save_tap` (diálogo nativo, escribe con `newline='\n'`); servidor
    `POST /api/cnc_toolpath` y `/api/tap` (descarga como blob).
  - UI: **pestaña "CNC" propia en el sidebar** (Propiedades/Capas/CNC — pedida por Jose; el tab
    solo aparece en modo CNC, se auto-enfoca al entrar y te saca de él al salir). Contiene
    Material, Herramienta y "Corte · Perfil" (segmentado Fuera/Dentro/Línea, Prof. que
    **sigue sola al grosor del material** mientras no la edites, contador de pasadas), botón
    "◉ Ver trayectorias" (dibuja en azul el recorrido del CENTRO de la fresa; se invalida solo
    al cambiar geometría/fresa/lado vía `killPrev()` en pushUndo/restore/loaders), y "Exportar
    HPGL" se convierte en **"Exportar G-code"** en modo CNC (mismo botón, `btnSaveLbl`).
- **C. Vaciado, taladro, puentes — ✅ CONSTRUIDA 22-jul-2026** (verificada con pruebas unitarias +
  punta a punta; falta vistazo de Jose). **La rampa de entrada quedó FUERA a propósito** (la
  bajada lenta de la fresa la suple en MDF/PVC; retomarla si el acrílico da guerra). Qué se hizo:
  - `cnc_gcode.py`: **`make_pocket()`** — anillos concéntricos hacia adentro por zona conexa
    (paso = `stepover_pct` de la fresa, % del Ø, default 40), del centro a la pared (pared al
    final = acabado limpio); respeta huecos anidados (holgura euclidiana exacta = radio).
    **`drill_points()`** — centro del bbox de cada contorno cerrado. **`build_drill()`** —
    picoteo: entre pasadas sube a +2mm a despejar viruta. **Puentes** en `build_gcode()`:
    `_split_ring()` parte el anillo por longitud de arco (n puentes de ancho w centrados lejos
    del arranque); solo actúan en pasadas más profundas que (prof − alto): la fresa sube al techo
    del puente con G01 y sigue. Anillos abiertos o pocket: sin puentes.
  - Backend: `_cnc_make()` despacha op profile/pocket/drill; preview devuelve también `drills`
    y `dia`. Fresas ganan `stepover_pct` (validado 10–90; las guardadas viejas caen a 40).
  - UI: segmentado **Operación (Perfil/Vaciado/Taladro)** en la pestaña CNC; Perfil muestra
    Fuera/Dentro/Línea + campos Puentes/Ancho/Alto (default 3×8×3, 0 = sin puentes); Vaciado y
    Taladro muestran nota explicativa. Taladros se previsualizan como círculo (Ø de la fresa) con
    cruz. Campo "Paso %Ø" en el modal de fresas.
  - **Ojo en pruebas de offsets:** medir holguras con distancia EUCLIDIANA al polígono (las
    esquinas se redondean con radio exacto); medir por ejes da falsos fallos en esquinas.
- **D. Preview con orden de corte, estimación de tiempo, optimización de recorrido.**
- **E. (futuro, decidir si vale)**: V-carve.

**Protocolo del primer corte real (no saltárselo):** archivo chico (cuadrado 100×100), primero
"corte en aire" (Z cero muy por encima del material) para verificar recorrido y orientación del
eje Y (misma duda pendiente que el plotter — [[design-studio]] "Eje Y"), luego corte real en
material de sacrificio. Revisar en el handle: G Code Setup → F Read = "Read F".

## Alcance acordado con Jose (22-jul-2026)
- **Trayectorias: Perfil + Vaciado (pocket) + Taladrado.** V-carve queda FUERA por ahora
  (Fase E opcional futura) → se quita la parte matemáticamente más dura del proyecto.
- **Husillo:** Jose no sabe cómo se controla (en Aspire ponía las RPM en la herramienta y ya).
  → Emitir `M03 S<rpm>` en el G-code y **verificar en la máquina** si obedece la S (recordar la
  trampa `S Read = Ign` del handle). Si no obedece, no rompe nada: el S se ignora y listo.
- **Materiales para presets de fresas:** MDF/triplay, acrílico, PVC espumado/coroplast y madera
  sólida. → La biblioteca de herramientas debe nacer con presets por material.

## Pregunta aún abierta
- Modelo exacto del controlador (A11/A11E/A15/A18 — está serigrafiado en el handle de la máquina).
  No bloquea nada: toda la familia A1X comparte la misma lista de G-code del manual.

Relacionado: [[design-studio]] (donde vivirá la función), [[estado]] (motor compartido).
