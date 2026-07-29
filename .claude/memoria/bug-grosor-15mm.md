---
name: bug-grosor-15mm
description: SIN RESOLVER — en Windows el grosor del material vuelve a 15 mm (el default) y no se deja cambiar; qué está descartado y qué medir
metadata: 
  node_type: memory
  type: project
  originSessionId: 21ab0256-37c6-4ef2-a2de-deb0c30ca8da
  modified: 2026-07-29T19:01:56.889Z
---

# 🔴 SIN RESOLVER: el grosor del material vuelve a 15 mm (Windows)

**Estado al 29-jul-2026, final del día.** Se abre sesión de Claude Code **en la propia Windows**
para medir ahí, porque desde el Mac ya se falló dos veces. Ver [[design-studio]].

## El síntoma (reportado por Jose)

En la PC de Windows, la pestaña **Configuración** del CNC muestra el **grosor del material en
15 mm**. Al cambiarlo y volver, **regresa a 15**. **No aparece ningún aviso ni error en pantalla.**

**15.0 es el valor de FÁBRICA** (`studio_backend.py`, `CNC_DEFAULTS['material']['thickness']`).
Que se vea 15 significa que `cnc_get()` **no encontró la config guardada** y cayó a los defaults.
⚠️ Ojo: `studio_ui.html` tiene además `<input id="matThick" value="15">` **escrito a mano en el
HTML** — el 15 puede venir de ahí si `paintCnc()` no llega a correr. Son dos fuentes distintas del
mismo número; hay que distinguirlas.

## Ya está DESCARTADO (probado, no supuesto)

Las tres capas pasan sus pruebas **en el Mac**:

| Capa | Prueba | Resultado |
|---|---|---|
| Migración de config | 4 escenarios con `sys.frozen` y HOME de mentira, en subprocesos | 4/4 |
| Backend (`cnc_set`/`cnc_get`) | Escribe a disco y relee | Persiste bien |
| Interfaz (el campo) | Arnés de DOM falso: pinta lo guardado, manda el cambio, lo conserva | 4/4 |

- **Jose SÍ instaló a mano** el zip de `v2026.07.29.5` (no con el botón, que está roto).
- **No es que la interfaz no mande el cambio**: el arnés confirma que `blur` → `cnc_set` con el
  valor correcto, y que el campo conserva lo que devuelve el backend.

## Dos intentos FALLIDOS (no repetirlos)

1. **`v2026.07.29.4`** — arreglé que `_migrar_config` era una **trampa de un solo tiro**: se
   disparaba `if not d.exists()` y la línea siguiente hacía `d.mkdir()`, así que si la carpeta
   nueva quedaba vacía la migración no se reintentaba jamás. **Era un defecto real y está
   arreglado**, pero **no resolvió esto**.
2. Antes de eso se sospechó del cambio de fabricante en sí. Tampoco.

## 👉 LO QUE HAY QUE MEDIR EN LA WINDOWS (siguiente paso)

Rutas de esa máquina:
- **Programa**: `%LOCALAPPDATA%\BuiltByJose\DesignStudio` (si actualizó con el botón en vez de
  reinstalar, puede seguir en `...\Antike\DesignStudio`)
- **Config**: `%APPDATA%\BuiltByJose\DesignStudio` — aquí van `cnc_config.json`,
  `plotter_config.json`, `fonts_cache.json`, `arranque.log`, `actualizar.log`
- **Config vieja**: `%APPDATA%\Antike\PlotterController` (de ahí copia la migración)

**Protocolo, en este orden:**

1. Ver qué versión está instalada de verdad (`version.txt` en la carpeta del programa).
2. Listar la carpeta de config **con `LastWriteTime`** y leer el grosor de `cnc_config.json`.
3. Abrir la app, poner el grosor en **7** (número que no se haya usado), clic fuera, **cerrar**.
4. Volver a listar.

**Cómo se lee el resultado:**

| Qué pasó | Dónde está el fallo |
|---|---|
| `LastWriteTime` se movió **y** dice 7 | Sí escribe → el fallo es al **LEER** |
| `LastWriteTime` **no** se movió | No escribe → el fallo es al **GUARDAR**, en silencio |
| La carpeta nueva no existe | La app no usa la ruta esperada |
| `version.txt` ≠ `2026.07.29.5` | No es la versión que se cree; todo lo demás sobra |

**Ventaja de estar en la Windows**: se puede correr `DesignStudio.exe --diagnostico`, leer
`arranque.log`, y sobre todo **correr la app desde el código** (`python design_studio.py`) para ver
los errores en vivo — que compilada no se ven porque **se distribuye sin consola**.

## La lección que rige aquí

**Cinco teorías cayeron el 28-jul razonando desde el Mac; la instrumentación lo resolvió al primer
intento.** Con este bug ya van **dos** intentos fallidos por el mismo camino. **Medir en la máquina
que falla, no deducir desde la que funciona.** Y un fallo que solo ocurre en una máquina no está en
el código: está en el encuentro entre el código y ESA máquina.
