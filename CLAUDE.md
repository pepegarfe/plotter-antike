# CLAUDE.md — Plotter Antike

Leer este archivo **antes** de cualquier modificación al proyecto.

---

## Descripción general

Aplicación de escritorio Python/tkinter para controlar un plotter de corte
a través de un puerto COM/USB. El usuario abre un archivo vectorial (SVG, AI, DXF),
lo previsualiza, ajusta posición y área de trabajo, y envía el diseño al plotter via HPGL.

**Archivo principal**: `plotter_control.py` (~2500 líneas, un único archivo monolítico).
**No hay módulos externos propios** — todo el código está en ese archivo.

---

## Archivos del proyecto

```
plotter_stm/
├── plotter_control.py       # Aplicación completa
├── requirements.txt         # pyserial, svgpathtools, ezdxf, pymupdf
├── instalar_dependencias.bat
├── crear_icono.py           # Genera icon.ico con Pillow
├── PlotterAntike.spec       # Config de PyInstaller
├── build.bat                # Compila el exe (corre en la máquina del desarrollador)
├── instalar.bat             # Instalador para el usuario final
├── instalar.ps1             # Lógica del instalador (PowerShell)
└── CLAUDE.md                # Este archivo
```

### requirements.txt
```
pyserial>=3.5
svgpathtools>=1.6
ezdxf>=1.1
pymupdf>=1.24
```
Todas las dependencias son opcionales en tiempo de importación — la app arranca sin ellas
pero deshabilita la funcionalidad correspondiente (HAS_SERIAL, HAS_SVG, HAS_DXF, HAS_MUPDF).

---

## Arquitectura de clases

### Módulo-level helpers (antes de cualquier clase)

| Símbolo | Línea | Descripción |
|---|---|---|
| `_parse_svg_color(s)` | ~70 | String SVG → (r,g,b) float 0‥1, None si transparent |
| `_rgb_hex(rgb)` | ~97 | (r,g,b) → '#rrggbb' |
| `_style_from_svg_attrs(attrs)` | ~102 | Extrae fill/stroke del dict de svgpathtools |
| `_parse_svg_transform(s)` | ~117 | String transform SVG → 6-tupla (a,b,c,d,e,f) |
| `_compose_mtx(m1, m2)` | ~155 | Composición de matrices afines |
| `_apply_mtx(pts, mtx)` | ~163 | Aplica matriz a lista de (x,y) |
| `_resource(filename)` | ~20 | Ruta a recurso bundleado: `sys._MEIPASS/f` si exe, `__file__/../f` si script |
| `_config_path()` | ~25 | Ruta persistente al JSON de config: AppData si exe, dir del script si no |
| `_pinch_corners(pts, threshold_deg)` | antes de `_BaseCanvas` | Duplica puntos en esquinas agudas para B-spline con `smooth=True` |

#### `_pinch_corners(pts, threshold_deg=25.0)`
Permite usar `smooth=True` en `create_line` (necesario para que los arcos muestreados se vean curvos)
sin que los ángulos rectos/agudos se redondeen. Funciona duplicando el punto en cada esquina detectada:
en el B-spline de tkinter, el midpoint de dos puntos iguales coincide con el punto, creando un cusp exacto.

```python
cos_t = math.cos(math.radians(threshold_deg))  # cos(25°) ≈ 0.906
```

**CRÍTICO**: El umbral usa `cos(threshold_deg)`, NO `cos(180 - threshold_deg)`. Con threshold=25°:
- ángulo de 90° → dot product = cos(90°) = 0 < 0.906 → **se pincha** (correcto)
- ángulo de 15° → dot product ≈ 0.966 > 0.906 → **no se pincha** (correcto, es parte de un arco)

El valor 25° fue elegido porque DXF ARC/CIRCLE usa mínimo 24 segmentos/círculo = 15°/paso;
así todos los arcos bien muestreados (≤15°) permanecen suaves, y las esquinas reales (≥30°) se pinzan.

**Caché**: el resultado se guarda en `d['_pinched']` dentro del styled dict. Se invalida automáticamente
cuando `_effective_styled()` crea dicts nuevos al aplicar transforms. **No llamar `_pinch_corners`
en cada redraw sin caché** — es costoso en paths con muchos puntos.

### `HPGLConverter`
Convierte paths vectoriales a comandos HPGL.
- `UNITS_PER_MM = 40` (1 unidad HPGL = 0.025 mm)
- `__init__(speed, pressure, overcut_mm=0.0)` — `overcut_mm` aplica a todos los paths
- `initialize()` → emite `IN; SP1; VS{speed}; FS{pressure};`
- `add_path(points)` → `PU x,y; PD x,y; ... PU;` (puntos en mm). En trazados cerrados (primer punto ≈ último punto, tolerancia 0.1 mm) con `overcut_mm > 0`, continúa cortando desde el inicio la distancia configurada antes del `PU;` final.
- `finalize()` → `PU0,0; SP0;`
- `test_square(size_mm)` → cuadrado de prueba

**Sobrecore (`overcut_mm`):** detecta trazado cerrado cuando `dist(pts[0], pts[-1]) < 0.1`. Luego recorre pts[0]→pts[1]→… acumulando distancia hasta cubrir `overcut_mm`, interpolando el punto exacto en el último segmento. Garantiza que el punto de inicio quede completamente cortado.

### `SVGParser`
Parser SVG propio basado en `xml.etree.ElementTree` (NO svgpathtools como primario).
- `PX_TO_MM = 0.264583` (96 DPI)
- `_SKIP_TAGS` = defs, clipPath, mask, symbol, pattern, marker
- **`parse(filepath)`** → siempre llama `_parse_basic()`, devuelve `List[dict]`
- **`_parse_basic()`** → calcula `_root_mtx`, hace walk recursivo del XML
- **`_root_mtx(root)`** → matriz user-units→mm desde viewBox + width/height del SVG
- **`_walk(elem, result, fill, stroke, mtx)`** → recorre el árbol propagando transforms y estilos
- **`_parse_d(d)`** → parser completo de atributo `d` de SVG path, devuelve `List[List[(x_uu, y_uu)]]` en user units (NO multiplica por PX_TO_MM — la matriz lo hace)
- Comandos soportados: M/m L/l H/h V/v C/c S/s Q/q T/t A/a Z/z (todos)
- Z/z guarda el subpath y continúa (no hace break)
- `_arc_pts()` → implementación completa del SVG endpoint-to-center arc
- Shape parsers (`_parse_rect`, `_parse_circle`, `_parse_line`, `_parse_poly`) devuelven user units crudas (sin PX_TO_MM)
- `_dedup()` → elimina paths duplicados por huella de coordenadas

**CRÍTICO**: Los parsers de shapes NO multiplican por `PX_TO_MM` — eso lo hace `_root_mtx` vía la matriz afín. No agregar `* self.PX_TO_MM` ahí.

### `DXFParser`
- Usa `ezdxf` para leer archivos DXF del modelspace
- `_TOL = 0.01` — desviación máxima cuerda-arco en unidades DXF (≈ mm)
- `_CHAIN_TOL = 0.01` — tolerancia para fusionar extremos de segmentos en `_chain_paths`
- Entidades soportadas: LINE, LWPOLYLINE (con bulge → arcos), POLYLINE, CIRCLE, ARC, ELLIPSE, SPLINE, INSERT (bloques recursivos hasta depth=12)
- **LWPOLYLINE y POLYLINE**: usan `entity.virtual_entities()` para descomponer segmentos con bulge en LINE+ARC reales. Sin esto, bulge se ignora y las curvas se vuelven líneas rectas.
- **ARC/CIRCLE**: muestreo por tolerancia geométrica: `n = π/acos(1-tol/r)`. Mínimo 24 segmentos para círculos completos, 8 para arcos parciales.
- **ELLIPSE/SPLINE**: `flattening(0.01)`
- **INSERT**: expandido recursivamente vía `virtual_entities()` con límite depth=12
- **`_chain_paths(paths)`** — fusiona segmentos conectados extremo-a-extremo en un único `create_line`. Elimina los artefactos visuales de "corte" que aparecen cuando dos `create_line` separados comparten un punto (cada uno dibuja su propio cap redondeado solapándose).
- `_collect(entity, result, color, depth)` — dispatcher recursivo
- **`_INSUNITS_TO_MM`** — dict que mapea el valor de `$INSUNITS` del header DXF al factor de conversión a mm. Valores clave: 0=unitless(1.0), 1=pulgadas(25.4), 4=mm(1.0), 5=cm(10.0), 6=metros(1000.0).
- **`parse()`** lee `doc.header['$INSUNITS']`, obtiene el factor de escala, parsea todas las entidades, aplica `_chain_paths`, y si `scale != 1.0` multiplica todas las coordenadas por el factor antes de devolver. Esto corrige archivos en cm que aparecerían al 10% del tamaño real si se leyeran sin conversión.

### `AIParser`
- Usa `pymupdf` (fitz) — lee archivos .AI (CS4+) como PDF
- `PT_TO_MM = 0.352778` (1 PDF point = 0.352778 mm)
- `page.get_drawings()` → cada drawing es un path lógico
- Maneja: moveto (m), lineto (l), cubic bezier (c), rect (re), quad (qu)
- Deduplicación por huella de coordenadas

### `PlotterController`
- `connect(port, baudrate)` → pyserial con `xonxoff=True` (flow control XON/XOFF)
- `send(cmd)` → escribe ASCII + flush
- `send_hpgl(hpgl, progress_cb)` → envía línea por línea con sleep(0.01)
- `move_relative(direction, dist_mm)` → PR{x},{y}; en unidades HPGL
- `abort()` → ESC + IN;

### `_BaseCanvas`
Infraestructura compartida de zoom/pan/grilla para los dos canvas.
- Sistema de coordenadas: `_to_canvas(x_mm, y_mm)` → `(cx, cy)` canvas pixels
  - `cx = x_mm * zoom + off_x`
  - `cy = off_y - y_mm * zoom` (Y invertido: mm crece hacia arriba, canvas hacia abajo)
- **`_auto_fit()`** → cuando hay puntos de diseño, encuadra sobre ellos. Cuando no hay diseño pero sí área de trabajo, usa las esquinas `(0,0)` y `(work_w, work_h)` como referencia — así el canvas arranca mostrando el cuadrante positivo con el origen abajo-izquierda.
- **`set_work_area(w_mm, h_mm)`** → actualiza `_work_w`, `_work_h`. Si hay diseño cargado llama `redraw()`; si no, llama `_auto_fit()` para reencuadrar sobre el área.
- **`_draw_grid()`** — espaciado adaptativo: elige el paso más pequeño de `(1,2,5,10,20,50,100,200)` mm tal que `zoom * step >= 30px`. Sólo dibuja las líneas cuyo pixel cae dentro de `[0, w]` o `[0, h]` (culling de visibilidad). Genera ~20-40 ítems en lugar de los ~500 sin culling.
- `_draw_origin()` → elementos visuales fijos
- `_draw_work_area_bg()` → rectángulo de fondo celeste (#eef4ff) del área de trabajo
- `_draw_work_area_border()` → borde discontinuo azul (#4488cc) con etiqueta de dimensiones
- Bindings base: rueda = zoom; `<ButtonPress-1>` + `<B1-Motion>` = pan (sobreescrito en DesignCanvas); `<ButtonPress-2>` + `<B2-Motion>` = pan con botón central (siempre activo)
- `_drag_start` y `_drag_move` pueden ser sobreescritos en subclases (DesignCanvas lo hace)
- **Pan con botón central** — `_mid_drag_start` / `_mid_drag_move` / `_mid_drag_end`: independientes de `_drag`, siempre disponibles. Al presionar el botón central el cursor cambia a `fleur`; al soltar vuelve a `crosshair`.

### `DesignCanvas` — hereda `_BaseCanvas`
Muestra el diseño con colores y rellenos. Tiene dos modos de interacción con el botón izquierdo.

**Campos:**
- `styled: List[{"pts", "fill", "stroke"}]`
- `_selected: int` — índice del path con selección individual (naranja), -1 = ninguno
- `_select_cb: callable(idx)` — callback al seleccionar un path por clic (o -1 al deseleccionar)
- `pan_mode: bool` — False = modo selección (default); True = botón izquierdo hace pan
- `_sel_set: set` — índices de paths seleccionados por rubber-band (dibujados en azul)
- `_sel_set_cb: callable(set)` — callback con el conjunto de índices tras soltar el rectángulo
- `_rect_start`, `_rect_id` — estado interno del rectángulo en curso
- `cut_paths: List[pts]` — vectores de corte para el overlay (se actualiza junto con el diseño)
- `show_cut: bool` — si True, dibuja `cut_paths` encima del diseño en azul (#0055cc)

**Overlay de vectores de corte:**
`show_cut` se activa con el Checkbutton "✂ Vectores" en la toolbar de Vista Previa.
Cuando está activo, al final de `redraw()` se dibujan los paths de `cut_paths` usando
`_pinch_corners` + `smooth=True` en azul, sin necesidad de abrir un Toplevel separado.
`cut_paths` debe mantenerse sincronizado con `_effective_styled()` cada vez que cambie el diseño.

**Modos de botón izquierdo:**
- `pan_mode=False` (default): clic (≤5px) = selección individual (`_do_select`); arrastrar >5px = dibuja rectángulo punteado azul; al soltar → `_sel_set_cb(indices)`. Clic en vacío deselecciona.
- `pan_mode=True`: arrastrar = pan (igual que botón central). El botón central siempre hace pan independientemente del modo.

**Métodos sobreescritos de _BaseCanvas:**
- `_drag_start`: si `pan_mode`, inicia pan normal; si no, inicia rubber-band y suprime pan (`self._drag = None`)
- `_drag_move`: si `pan_mode`, mueve el viewport; si no, actualiza rectángulo de selección
- `_sel_release`: si `pan_mode`, limpia `_drag` y retorna; si no, procesa clic individual o rubber-band según distancia arrastrada (umbral 5px)

**Colores en `redraw()`:**
- Path seleccionado individualmente (`_selected`): naranja `#ff6600`, width=2.5
- Path en `_sel_set` (grupo rubber-band): azul `#2266ee`, width=2.0
- Resto: color original del path

**`create_line` usa `smooth=True`** para que los arcos muestreados como polígonos se vean curvos.
Las esquinas agudas se preservan vía `_pinch_corners` con caché en `d['_pinched']`.

**`set_paths(styled, selected=-1)`** debe llamarse con `_effective_styled()` (no con `current_styled` raw), para que `_auto_fit` encuadre las coordenadas ya con offset aplicado.

**Tecla Delete:** el canvas tiene `takefocus=True`. `<ButtonPress-1>` llama `focus_set()` para que
el canvas capture el teclado. `<Delete>` dispara `_delete_selected()` en `PlotterApp`.

### `CutCanvas` — hereda `_BaseCanvas`
Muestra los vectores de corte en azul (#0055cc). Ya no es la vista principal de corte
(reemplazada por el overlay en `DesignCanvas`), pero el código permanece por si se necesita
en el futuro. `_show_cut_preview()` aún existe pero el botón de la toolbar es ahora un Checkbutton
que activa el overlay en lugar de abrir este popup.
- `paths: List[List[(x,y)]]`
- `set_paths(styled)` → extrae solo las coordenadas
- `redraw()`: usa `smooth=True` en `create_line`

### `PlotterApp` — clase principal
Estado relevante:
```python
self.current_styled  = []     # List[dict] paths parseados
self.current_hpgl    = ""     # string HPGL generado
self.current_file    = ""     # path al archivo abierto
self.path_offsets    = []     # [[dx,dy], ...] offset por path en mm
self.path_scales     = []     # [scale, ...] 1.0=original
self.path_rotations  = []     # [degrees, ...] 0.0=sin rotación; CCW
self._sel_idx        = -1     # índice seleccionado individualmente, -1 = ninguno
self._sel_set        = set()  # índices seleccionados por rubber-band (grupo manual)
self._undo_stack     = []     # historial de estados para Ctrl+Z (máx 50)
self._redo_stack     = []     # estados revertidos para Ctrl+Shift+Z
self._cut_win        = None   # Toplevel del popup de vectores de corte (legacy)
self.cut_canvas      = None   # CutCanvas, creado lazily en _show_cut_preview() (legacy)
# Tkinter variables relevantes:
# var_overcut: DoubleVar — distancia de sobrecore en mm (0 = desactivado)
```

#### Config persistente
- `_CONFIG_PATH` (atributo de clase) = `_config_path()` — JSON con `work_w`, `work_h`, `port` y `baud`.
- `_load_config()` → lee el JSON al iniciar; carga `var_work_w`/`var_work_h`, y también `var_port`/`var_baud` si están guardados.
- `_save_config()` → escribe el JSON con `work_w`, `work_h`, `port` y `baud` en cada confirmación de área de trabajo **y** al conectar/reconectar al plotter.
- Al arrancar la app se muestra `_ask_work_area_startup()` — diálogo modal centrado, pre-llenado con los valores guardados. El usuario puede confirmar o cambiarlos. No tiene botón Cancelar.
- Desde el menú Archivo → "Área de trabajo…" se llama `_open_work_area_dialog()` — mismo diálogo con botón Cancelar adicional.

#### Reconexión automática — `_ensure_connection()`
Llamado por `send_design()` (y cualquier otra acción que requiera el plotter) antes de enviar.
- Si ya hay conexión activa: retorna `True` inmediatamente.
- Si no hay puerto configurado: muestra aviso y retorna `False`.
- Si hay puerto: pregunta al usuario si desea reconectar a `{port} @ {baud}`.
  - Si acepta: conecta, actualiza UI (LED, status bar, log), envía `IN;`, guarda config → retorna `True`.
  - Si cancela: retorna `False`.
- En caso de error de conexión: muestra `showerror` y retorna `False`.

#### Eliminación de paths — `_delete_selected()`
Dispara con la tecla `<Delete>` cuando el canvas tiene foco.
- Modo individual (`_sel_idx >= 0`): elimina ese path.
- Modo grupo rubber-band (`_sel_set` no vacío): elimina todos los paths del conjunto.
- Modo "Todos" (ambos vacíos): no hace nada (evita borrado accidental de todo el diseño).

Tras eliminar:
1. Reconstruye `current_styled`, `path_offsets`, `path_scales`, `path_rotations` con los índices restantes (`keep`).
2. Resetea `_sel_idx`, `_sel_set`, `design_canvas._sel_set`, `design_canvas._selected`.
3. Repobla `cb_obj` con los objetos restantes y resetea a "Todos".
4. Si quedan paths: llama `_effective_styled()`, actualiza `design_canvas.cut_paths`, llama `set_paths()`, actualiza `lbl_info`.
5. Si no quedan paths: llama `set_paths([])` y actualiza `lbl_info` a "Sin diseño".

#### Tres modos de selección / transformación

Las transformaciones (posición, escala, rotación, tamaño) tienen **tres modos** según el estado:

| Condición | Modo | Comportamiento |
|---|---|---|
| `_sel_idx >= 0` | **Individual** | Transforma solo ese path. Escala = ABSOLUTA (100% = tamaño original). Rotación = ABSOLUTA. |
| `_sel_set` no vacío | **Grupo manual** | Transforma solo los paths del conjunto. Escala/rotación RELATIVAS. Resetea var_scale/var_rotate a 100/0 tras aplicar. |
| ambos vacíos | **Todos** | Transforma todos los paths como un grupo. Escala/rotación RELATIVAS. Resetea var_scale/var_rotate a 100/0 tras aplicar. |

El modo "Grupo manual" usa la **misma matemática de grupo** que "Todos", pero solo sobre los índices de `_sel_set`. Los paths fuera del conjunto no se tocan.

**Anchor de escala (modos Grupo y Todos):** el pivot es la esquina inferior-izquierda del bbox del grupo (`ax = min_x`, `ay = min_y` del conjunto efectivo). La fórmula analítica para cada path `i` con centro original `(ocx, ocy)` y offset actual `(dx, dy)` es:
```python
new_dx = (ax - ocx) * (1 - s) + s * dx
new_dy = (ay - ocy) * (1 - s) + s * dy
path_scales[i] *= s
```
Esto garantiza que todos los paths escalen como grupo alrededor del anchor sin romper las posiciones relativas entre ellos.

#### Métodos clave de transformación

- **`_effective_styled()`** → aplica offset + scale + rotation a `current_styled`; orden: scale→rotate (sobre centro del bbox original) → translate(offset). No modifica `current_styled`.
- **`_refresh_preview()`** → actualiza `design_canvas.styled` con effective + redibuja + regenera HPGL + actualiza displays de size y scale. **Sin** reset de zoom. También actualiza `design_canvas.cut_paths` para mantener el overlay sincronizado.
- **`_update_pos_display()`** → calcula min(x), min(y) del bbox efectivo del contexto activo y los pone en `var_pos_x`/`var_pos_y`. Llama a `_update_size_display()` y `_update_scale_display()`.
- **`_update_size_display()`** → W×H del bbox efectivo del contexto activo → `var_size_w`/`var_size_h`.
- **`_update_scale_display()`** → muestra scale/rotation del path individual; si modo grupo o todos, muestra 100/0.
- **`_apply_obj_position(*_)`** → mueve el contexto activo al (x,y) de `var_pos_x`/`var_pos_y`.
- **`_apply_scale(*_)`** → tres ramas según contexto.
- **`_apply_rotation(*_)`** → tres ramas según contexto.
- **`_orig_size(idx)`** → (w_mm, h_mm) de path(s) a scale=1.0 sin offset. Acepta idx≥0 (individual), idx<0 con `_sel_set` (subgrupo), idx<0 sin sel_set (todos).
- **`_apply_size_w(*_)` / `_apply_size_h(*_)`** → calcula `var_scale` necesario y llama `_apply_scale`. Modo individual: factor absoluto; modo grupo/todos: factor relativo.
- **`_nudge_pos/scale/rotate`** → incrementan el spinbox correspondiente y llaman al apply.
- **`_center_design()`** → centra el contexto activo en el área de trabajo.
- **`_reset_positions()`** → zeros en offsets/scales/rotations, luego **re-aplica la normalización al cuadrante positivo** (igual que `open_file`) para que el diseño no quede en coordenadas negativas. Limpia `_sel_set` y resetea combobox a "Todos".

#### Métodos de selección y navegación

- **`_on_pan_mode_toggle()`** → sincroniza `design_canvas.pan_mode` con `_var_pan_mode`; cambia cursor a `hand2` (pan) o `crosshair` (selección).
- **`_on_canvas_sel_rect(indices)`** → callback desde `DesignCanvas._sel_set_cb`. Actualiza `_sel_set`, agrega/quita "Selección" del combobox, redibuja y actualiza displays.
- **`_clear_sel_set()`** → limpia `_sel_set`, quita "Selección" del combobox, actualiza `var_obj_sel` si es necesario.
- **`_arrow_nudge(axis, direction)`** → mueve el objeto/grupo seleccionado con las teclas de flecha. Solo actúa cuando `_sel_idx >= 0` o `_sel_set` no vacío; en modo "Todos" no hace nada para evitar mover todo el diseño accidentalmente. Delega a `_nudge_pos`.

#### Sistema de deshacer (Ctrl+Z)

- **`_UNDO_MAX = 50`** — número máximo de pasos guardados en cada stack.
- **`_push_undo()`** — limpia `_redo_stack` (nueva acción invalida el historial de redo), luego guarda un snapshot de `current_styled`, `path_offsets`, `path_scales`, `path_rotations`. Usa copias superficiales de un nivel (`[dict(d) for d in ...]`, `[list(o) for o in ...]`).
- **`_undo()`** — guarda el estado actual en `_redo_stack`, luego restaura el último snapshot de `_undo_stack`: reconstruye todas las listas de estado, resetea `_sel_idx`, `_sel_set`, `cb_obj`, `var_scale`, `var_rotate`, regenera HPGL y actualiza el canvas.
- **`_redo()`** — guarda el estado actual en `_undo_stack`, luego restaura el último snapshot de `_redo_stack`. Misma lógica de restauración que `_undo()`.
- **Bindings:** `<Control-z>` → `_undo()`, `<Control-Z>` (Shift+Z) → `_redo()`.
- **`_push_undo()` se llama en los métodos apply**, no en los nudge. Los nudge llaman a apply, que ya empuja. Llamarlo en nudge generaría el doble de entradas.
- **Al abrir un archivo** (`open_file()`): `self._undo_stack = []; self._redo_stack = []` — limpia ambos historiales.
- **Operaciones que llaman `_push_undo()`**: `_apply_obj_position`, `_apply_scale`, `_apply_rotation`, `_reset_positions`, `_delete_selected`.

#### Métodos de preview

- **`_toggle_cut_overlay()`** → sincroniza `design_canvas.show_cut` con `_var_cut_overlay` y llama `redraw()`. No abre ningún Toplevel.
- **`_fit_view()`** → solo hace `_auto_fit` del `design_canvas`.
- **`_zoom(factor)`** → solo zooms el `design_canvas`.
- **`_show_cut_preview()`** / **`_zoom_cut(factor)`** → legacy; el popup de CutCanvas ya no está expuesto en la UI.
- **`_set_led(on)`** → actualiza el LED verde/rojo del tab Plotter y llama `_set_sb_led(on)`.
- **`_set_sb_led(on)`** → actualiza el círculo azul/rojo de la barra de estado inferior. Azul `#0077cc` = conectado, rojo `#cc2222` = desconectado. Guard `hasattr(self, 'sb_led')` porque `_set_led` se llama durante la construcción del tab Plotter antes de que `_build_statusbar` cree `sb_led`.

#### Layout — UI

**No hay panel izquierdo.** Todos los controles están en 3 filas de toolbar dentro del tab "Vista Previa".
El canvas ocupa todo el espacio restante. Geometría inicial: 1380×780 px, mínimo 1100×640 px.

**Notebook** (ocupa todo el ancho):

**Tab "Vista Previa"** — 3 filas de toolbar + canvas a pantalla completa:

- **Toolbar 1 — Objeto / Acciones:**
  - "Objeto:" + `cb_obj` (combobox de selección) + separador
  - [Test 10×10 mm] [Enviar Diseño ▶] [Cancelar]
  - (Abrir archivo y Ver HPGL están en el menú Archivo, no en la toolbar)

- **Toolbar 2 — Posición:**
  - X (mm): spinbox + [<][>]  Y (mm): spinbox + [v][^]  Paso: combobox
  - [Centrar en área] [Resetear todo]

- **Toolbar 3 — Tamaño / Escala / Rotación / Vista:**
  - W: spinbox mm  H: spinbox mm + separador
  - Escala: spinbox % [-][+] paso_combo% + separador
  - Rot: spinbox ° [<<][>>] paso_combo° + separador
  - [Ajustar] [+] [−]  [↔ Mover]  [✂ Vectores]  + `lbl_info` (derecha)

**Tab "Plotter"** — Conexión (puerto COM, baudrate, conectar/desconectar) + Control Manual (flechas, pluma, origen) + Parámetros de Corte (velocidad, presión, sobrecore)

**Barra de estado inferior** — círculo azul/rojo (`sb_led`) + texto de estado (`var_status`) + barra de progreso

**Tab "Log COM"** — log de comunicación serial

**Área de trabajo**: configurada exclusivamente via diálogo (al inicio o Archivo → Área de trabajo…).

#### `open_file()`
1. Parsea el archivo según extensión (.svg → SVGParser, .dxf → DXFParser, .ai → AIParser)
2. Inicializa `path_offsets`, `path_scales`, `path_rotations`
3. Limpia `_sel_set` y `design_canvas._sel_set`
4. **Normaliza al cuadrante positivo**: calcula `min_x`, `min_y` de todos los paths y ajusta todos los offsets para que `min_x ≥ 0` y `min_y ≥ 0`
5. Pobla `cb_obj` con `["Todos"] + ["Objeto N" for N]`
6. Conecta `design_canvas._select_cb = self._on_canvas_select`
7. Llama `design_canvas.set_paths(self._effective_styled(), selected=-1)` — **con effective**, no raw
8. Actualiza `design_canvas.cut_paths` con los pts del effective
9. Si `cut_canvas` existe (popup legacy abierto), lo actualiza también
10. Llama `_generate_hpgl()` y `_update_pos_display()`

`_generate_hpgl()` usa `_effective_styled()`, no `current_styled` directamente.

---

## Convenciones críticas

### Sistema de coordenadas
- Todos los parsers devuelven coordenadas en **mm**.
- Excepción interna en SVGParser: `_parse_d` y shape parsers devuelven **user units** — la conversión a mm ocurre en `_root_mtx` vía la matriz afín en `_walk`.
- El canvas usa Y-invertido: mm crecen hacia arriba, pixels hacia abajo.
- Al cargar, los diseños se normalizan para que todo esté en coordenadas positivas (X≥0, Y≥0).
- Al abrir la app sin diseño, el canvas muestra el área de trabajo en el cuadrante positivo (origen abajo-izquierda).

### Formato de datos interno
```python
# Un "styled path"
{
    "pts":      [(x_mm, y_mm), ...],  # al menos 2 puntos
    "fill":     (r, g, b) | None,     # None = sin relleno
    "stroke":   (r, g, b) | None,     # None = sin contorno
    "_pinched": [...] | None,         # caché de _pinch_corners; None = no calculado aún
}
```

### HPGL
- 1 mm = 40 unidades HPGL
- Flujo: `IN; SP1; VS{speed}; FS{pressure}; [PU x,y; PD x,y; ... PU;]* PU0,0; SP0;`
- XON/XOFF flow control activado en pyserial

### Config persistente (JSON)
```json
{ "work_w": 300.0, "work_h": 200.0, "overcut": 1.0, "port": "COM3", "baud": "9600" }
```
`port` y `baud` se guardan al conectar al plotter y se restauran al iniciar. `overcut` se guarda al conectar/confirmar área de trabajo.

### Atajos de teclado

| Atajo | Acción |
|---|---|
| `Ctrl+O` | Abrir archivo |
| `Ctrl+Z` | Deshacer |
| `Ctrl+Shift+Z` | Rehacer |
| `Ctrl+=` / `Ctrl++` | Zoom in ×1.25 |
| `Ctrl+-` | Zoom out ×0.8 |
| `↑ ↓ ← →` | Mover objeto/grupo seleccionado (solo si hay selección activa) |
| `Delete` | Eliminar path(s) seleccionado(s) |
| Rueda ratón | Zoom en canvas |
| Botón central + arrastrar | Pan del canvas (siempre disponible) |

### UI
- Sin panel izquierdo. Notebook ocupa todo el ancho de la ventana.
- Todos los controles de transformación/acciones viven en 3 filas de toolbar dentro del tab "Vista Previa".
- Notebook con tabs "Vista Previa", "Plotter" y "Log COM"
- Vista Previa: DesignCanvas a pantalla completa; overlay de corte via Checkbutton (no popup)
- `_refresh_preview()` actualiza sin reset de zoom — **NO** llamar `set_paths()` para refrescos de posición
- `cut_canvas` puede ser `None` — siempre guardar con `if self.cut_canvas:` antes de usar

---

## Dependencias opcionales y flags

| Flag | Librería | Funcionalidad |
|---|---|---|
| `HAS_SERIAL` | pyserial | Conexión COM, envío HPGL |
| `HAS_SVG` | svgpathtools | Solo para `_parse_with_lib()` (no se usa como primario) |
| `HAS_DXF` | ezdxf | Abrir archivos .dxf |
| `HAS_MUPDF` | pymupdf (fitz) | Abrir archivos .ai |

La app arranca y funciona sin ninguna dependencia; solo muestra advertencias al intentar usar la funcionalidad faltante.

---

## Qué NO hacer

- **No agregar `* self.PX_TO_MM`** en `_parse_d`, `_parse_rect`, `_parse_circle`, `_parse_line` o `_parse_poly` — la conversión la hace la matriz en `_walk`.
- **No llamar `_auto_fit()` o `set_paths()`** cuando solo se actualiza la posición, escala o rotación — usar `_refresh_preview()` para no perder el zoom del usuario.
- **No llamar `set_paths(current_styled)`** — siempre pasar `_effective_styled()` para que el auto-fit use las coordenadas con offset ya aplicado.
- **No usar svgpathtools como parser primario** — `parse()` siempre llama `_parse_basic()`. `_parse_with_lib()` existe pero no se invoca.
- **No romper el Z/z de `_parse_d`** — el comando cierra el subpath actual y sigue parseando (no hace break).
- **No separar el código en múltiples archivos** sin pedido explícito — el usuario trabaja con un único archivo.
- **No agregar comentarios extensos** — solo cuando el WHY no es obvio.
- **No acceder a `self.cut_canvas` sin guard** — puede ser `None` si el popup no está abierto.
- **No agregar `smooth=False`** en los `create_line` de los canvas — `smooth=True` es necesario para que los arcos DXF muestreados se vean curvos.
- **No resetear offsets a `[0,0]` directamente** en `_reset_positions` — siempre re-aplicar la normalización al cuadrante positivo después, para que el diseño no aparezca en Y negativo.
- **No hardcodear rutas de recursos o config** — usar `_resource()` y `_config_path()` para que funcione tanto como script como exe de PyInstaller.
- **No llamar `_pinch_corners` en cada redraw sin caché** — guardar en `d['_pinched']`; los dicts se recrean en `_effective_styled()` invalidando la caché automáticamente.
- **No usar `cos(180 - threshold_deg)` en `_pinch_corners`** — el umbral correcto es `cos(threshold_deg)`. Con `cos(180-25°) ≈ -0.906`, un ángulo de 90° (dot=0) nunca se detectaría.
- **No abrir un Toplevel para los vectores de corte** — la función está implementada como overlay (`show_cut`) en el propio `DesignCanvas`. `_show_cut_preview()` es legacy y no está expuesta en la UI.
- **No olvidar actualizar `design_canvas.cut_paths`** cuando cambie el diseño — se debe sincronizar junto con `design_canvas.styled` para que el overlay refleje el estado actual.
- **No llamar `_push_undo()` en los métodos nudge** — los nudge llaman a apply, que ya empuja. Hacerlo en nudge duplicaría las entradas del historial.
- **No olvidar limpiar ambos stacks en `open_file()`** — `self._undo_stack = []; self._redo_stack = []` evita deshacer/rehacer a un diseño anterior al cargar uno nuevo.
- **No escalar grupos alrededor del centro** — el anchor correcto para modos Grupo y Todos es la esquina inferior-izquierda (`ax = min_x`, `ay = min_y`). Usar el centro rompe las posiciones relativas entre paths dentro del grupo.
- **No restaurar `sel_mode` en `DesignCanvas`** — ese campo fue eliminado. El modo de interacción del botón izquierdo se controla ahora con `pan_mode` (False = selección/rubber-band, True = pan).
- **No acceder a `self.sb_led` directamente en `_set_led`** — usar `_set_sb_led()` que ya tiene el guard `hasattr`. `_set_led` se llama antes de que `sb_led` exista durante el init.
- **No llamar `_arrow_nudge` en modo "Todos"** — la función ya tiene guard para evitarlo; mantenerlo así para no mover todo el diseño accidentalmente con las flechas del teclado.
- **No pasar `overcut_mm` al `HPGLConverter` del test de corte** — el test siempre usa un cuadrado simple sin sobrecore. Solo `_generate_hpgl()` usa `var_overcut`.

---

## Build y distribución

### Flujo de desarrollo
```
python plotter_control.py   # probar cambios directamente
```

### Flujo de distribución
```
build.bat                   # compila PlotterAntike.exe → dist/
dist\instalar.bat           # el usuario final ejecuta esto
```

`build.bat` hace:
1. Instala `pyinstaller` + `pillow`
2. Genera `icon.ico` via `crear_icono.py`
3. Compila con `python -m PyInstaller PlotterAntike.spec --noconfirm --clean`
4. Copia `instalar.bat` e `instalar.ps1` a `dist\`

`instalar.bat` / `instalar.ps1` hace:
1. Copia el exe a `%LOCALAPPDATA%\Antike\PlotterController\` (sin admin)
2. Crea acceso directo en el Escritorio
3. Crea acceso directo en el Menú de Inicio bajo "Antike"

### Rutas según contexto de ejecución

| | Como script | Como exe (PyInstaller) |
|---|---|---|
| Recursos (icon.ico) | `__file__/../icon.ico` | `sys._MEIPASS/icon.ico` |
| Config JSON | `__file__/../plotter_config.json` | `%APPDATA%\Antike\PlotterController\plotter_config.json` |

---

## Ejecución

```bash
python plotter_control.py
```

Requiere Python 3.8+ con tkinter. Las dependencias se instalan con:
```bash
pip install pyserial svgpathtools ezdxf pymupdf
```
o ejecutando `instalar_dependencias.bat`.
