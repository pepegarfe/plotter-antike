# CLAUDE.md — Plotter Antike

Leer **antes** de tocar el código. Aquí van solo los **invariantes y las trampas** que no se
deducen leyendo el código. La arquitectura (clases, métodos, UI) se descubre leyendo
`plotter_control.py` — **no** se documenta aquí para que no se pudra.

**Historia, decisiones y estado del trabajo → [[MEMORY]]** (`.claude/memoria/`, empezar por `estado.md`).

> Este doc fue **reescrito y verificado contra el código el 21-jul-2026** (el anterior describía una
> versión vieja: hablaba de una UI que ya no existe y de código muerto). Si vuelves a ver una
> afirmación que el código contradice, **corrígela aquí** — no la copies.

---

## Qué es

App de escritorio **Python/tkinter** (un solo archivo, `plotter_control.py`, ~3600 líneas) que
controla un **plotter de corte** por puerto serial/USB. Abre un vector (SVG, DXF, AI), deja
acomodarlo y lo envía al plotter en **HPGL**. Corre en Windows, Mac y Linux.

**Se distribuye compilada** (PyInstaller). No es una librería ni tiene módulos propios: todo vive en
ese archivo. **No separar en varios archivos sin pedido explícito.**

---

## Modelo de datos y coordenadas (convenciones, no obvias)

- **Todos los parsers devuelven coordenadas en milímetros.** Excepción interna en `SVGParser`:
  `_parse_d` y los parsers de shapes devuelven **user units** crudas; la conversión a mm la hace la
  **matriz afín** (`_root_mtx` mete el factor `PX_TO_MM`). ⚠️ **Nunca agregar `* PX_TO_MM`** en esos
  métodos: duplicarías la conversión.
- El canvas usa **Y-invertido**: en mm la Y crece hacia arriba; en pixels crece hacia abajo.
- Al cargar un archivo, el diseño se **normaliza al cuadrante positivo** (X≥0, Y≥0). Si reseteas
  posiciones, **re-aplica esa normalización** — no dejes offsets en `[0,0]` crudos, o el diseño
  aparece en Y negativa.
- **HPGL**: `UNITS_PER_MM = 40`. Serial con **XON/XOFF** activado.
- Un **"styled path"** es un dict con exactamente estas llaves útiles:
  ```python
  { "pts": [(x_mm, y_mm), ...],   # ≥2 puntos
    "fill":   (r,g,b) | None,
    "stroke": (r,g,b) | None }
  ```
  (Verás una llave `_pinched` escrita a `None` en algunos sitios: es un **vestigio muerto**, nadie
  la lee — ver "Código muerto" abajo.)

---

## Invariantes / Qué NO hacer (todo verificado contra el código)

- **No agregar `* PX_TO_MM`** en `_parse_d`, `_parse_rect`, `_parse_circle`, `_parse_line`,
  `_parse_poly` — la matriz ya convierte.
- **No usar `svgpathtools` como parser primario.** `SVGParser.parse()` siempre llama
  `_parse_basic()`, que usa `xml.etree` de la stdlib. `_parse_with_lib()` existe pero **no se
  invoca** (por eso el flag `HAS_SVG` casi no importa: el parser primario no depende de esa librería).
- **No romper el `Z/z` de `_parse_d`**: cierra el subpath actual y **continúa** parseando (no hace
  `break`).
- **Escalado de grupo (modos "Grupo" y "Todos"): el ancla es la esquina INFERIOR-IZQUIERDA** del bbox
  (`ax=min_x`, `ay=min_y`), **no el centro**. Usar el centro rompe las posiciones relativas entre
  trazados del grupo.
- **`_push_undo()` va en los métodos `_apply_*`, nunca en los `_nudge_*`** (los nudge delegan en
  apply, que ya empuja; hacerlo en ambos duplica el historial). **`open_file()` limpia ambos stacks**
  (`_undo_stack` y `_redo_stack`).
- **Rutas de recursos y config: usar `_resource()` y `_config_path()`**, nunca hardcodear. Es lo que
  hace que funcione igual como script y como exe de PyInstaller (config en AppData en Windows).
- **Refrescos de posición/escala/rotación: usar `_refresh_preview()`**, que NO resetea el zoom. **No
  llamar `set_paths()` ni `_auto_fit()`** para eso — perderías el zoom del usuario.
- **`set_paths()` y `_generate_hpgl()` siempre con `_effective_styled()`**, nunca con
  `current_styled` crudo. `_effective_styled()` aplica scale+rotación (sobre el centro del bbox
  original) y luego el offset, devolviendo dicts nuevos sin mutar el original.
- **Los `create_line` usan `smooth=False`** (con `joinstyle=MITER`, `capstyle=BUTT`). ⚠️ **No poner
  `smooth=True`**: fue eliminado a propósito para arreglar la fidelidad visual del corte. La
  suavidad de las curvas hoy viene del **muestreo denso de arcos**, no del spline de tkinter.
- **Tres modos de selección/transformación** según estado: **individual** (`_sel_idx >= 0`, escala y
  rotación ABSOLUTAS), **grupo manual** (`_sel_set` no vacío, RELATIVAS) y **todos** (ambos vacíos,
  RELATIVAS). Toda transformación debe respetar los tres.
- **El modo del botón izquierdo lo controla `pan_mode`** en `DesignCanvas` (False=selección/
  rubber-band, True=pan). El campo `sel_mode` **ya no existe** — no lo reintroduzcas. El botón
  central siempre hace pan.
- **Los vectores de corte son un OVERLAY dentro de `DesignCanvas`** (`show_cut` + `cut_paths`,
  dibujados en azul). **No abrir una ventana aparte para eso** — la clase `CutCanvas` y su andamiaje
  fueron eliminados. Mantener `cut_paths` sincronizado cada vez que cambie el diseño.
- **`_set_led` no debe tocar `self.sb_led` directo** — usar `_set_sb_led()`, que tiene guard
  `hasattr` (a `_set_led` se le llama antes de que exista el LED de la barra de estado).

---

## Dependencias opcionales

La app **arranca sin ninguna dependencia** y solo deshabilita la función que falte:

| Flag | Librería | Habilita |
|---|---|---|
| `HAS_SERIAL` | pyserial | Conexión al plotter y envío HPGL |
| `HAS_DXF` | ezdxf | Abrir `.dxf` |
| `HAS_MUPDF` | pymupdf (fitz) | Abrir `.ai` |
| `HAS_SVG` | svgpathtools | Solo `_parse_with_lib()`, que **no se usa** (el SVG primario va con stdlib) |

---

## Distribución y auto-actualización (operativo, no obvio)

- **CI en GitHub Actions** (`.github/workflows/release.yml`): al publicar un tag, compila solo el
  `.exe` de Windows y la app de Mac y los sube como assets del release.
- **Auto-update**: la app consulta `api.github.com/repos/pepegarfe/plotter-antike/releases/latest`,
  compara el `tag_name` contra `VERSION` (leída de `version.txt`) y ofrece descargar/instalar.
  - **El chequeo automático al arrancar SOLO corre en el exe compilado** (`sys.frozen`). Como script
    no se auto-revisa; el chequeo manual (menú Ayuda) sí funciona siempre.
  - `version.txt = "dev"` significa modo desarrollo local.

---

## Código muerto (no construir sobre esto; candidato a borrar)

- **`_pinch_corners()`** y la llave **`_pinched`**: vestigios de cuando se usaba `smooth=True`. Hoy
  nadie llama a la función y nadie lee la llave (solo se escribe a `None`). Si tocas esa zona, no
  asumas que hacen algo.

---

## Ejecución (desarrollo)

```bash
python plotter_control.py          # Python 3.8+ con tkinter
pip install pyserial ezdxf pymupdf # o instalar_dependencias.bat
```
