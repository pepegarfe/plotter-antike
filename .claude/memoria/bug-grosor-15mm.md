---
name: bug-grosor-15mm
description: RESUELTO 29-jul-2026 — el grosor volvía a 15 mm en Windows porque cnc_set() escribía cnc_config.json sin encoding='utf-8' y cp1252 no puede codificar el "″" de los nombres de fresa
metadata: 
  node_type: memory
  type: project
  originSessionId: 21ab0256-37c6-4ef2-a2de-deb0c30ca8da
  modified: 2026-07-29T19:51:34.430Z
---

# ✅ RESUELTO: el grosor del material volvía a 15 mm (Windows)

**Resuelto 29-jul-2026**, en sesión de Claude Code corriendo **en la propia Windows** (siguiendo la
regla de este archivo: medir en la máquina que falla). Ver [[design-studio]] y [[estado]].

## Causa raíz

`studio_backend.py` escribía `cnc_config.json` con `_cnc_path().write_text(json.dumps(cur, ...))`
**sin `encoding='utf-8'`**. Sin ese parámetro, `Path.write_text` usa el codepage por defecto del
sistema — en esta Windows, **cp1252**. Los nombres de fresa de fábrica incluyen
`'Fresa 3.175 mm (1/8″) · 1 filo'`, con `″` (U+2033, comilla doble tipográfica). **cp1252 no puede
codificar ese carácter.**

`cnc_set()` reescribe el dict COMPLETO (incluida la lista de fresas) en cada guardado, así que
**cualquier cambio en la pestaña CNC** disparaba la escritura. `Path.write_text` abre el archivo en
modo `'w'` (trunca de inmediato) y *luego* intenta codificar — al fallar la codificación, el archivo
quedaba **vacío (0 bytes)**, que es exactamente lo que se midió en ambas rutas de config (nueva y
vieja). `cnc_set` capturaba la excepción y devolvía `{'ok': False, 'error': ...}` (por eso Jose no
vio un aviso claro: probablemente un toast que no relacionó con el campo).

Después, `cnc_get()` intentaba leer ese archivo vacío; `json.loads('')` truena, pero está envuelto
en un `except Exception: pass` silencioso → cae a los defaults → **grosor siempre 15, sin aviso**.

**Por qué nunca falló en el Mac**: ahí el default de Python es UTF-8, no cp1252. Este bug es
100% específico de Windows — coincide con que las 3 capas habían pasado 4/4 en el Mac.

## El arreglo

Se agregó `encoding='utf-8'` explícito a las 6 lecturas/escrituras de `cnc_config.json` y del
autoguardado en `studio_backend.py` (líneas ~29, 34, 190, 201, 325, 653). **Commit:** ver git log
(`studio_backend.py`, 29-jul-2026, mensaje sobre encoding UTF-8 en cnc_config).

⚠️ **Regla para el futuro**: toda lectura/escritura de JSON en este proyecto debe llevar
`encoding='utf-8'` explícito (`read_text`/`write_text`/`open`). Sin eso, el default es el codepage
del SO — cp1252 en Windows, UTF-8 en Mac/Linux — y cualquier string con un carácter fuera de
cp1252 (tildes raras, comillas tipográficas, símbolos) revienta la escritura **en Windows
únicamente**, dejando el archivo truncado a 0 bytes. `autosave_load()` ya usaba `encoding='utf-8'`
al leer pero `autosave_save()` no al escribir — ese descuido delató el patrón.

## Cómo se probó (antes/después, en esta máquina)

Se escribió un script mínimo que importa `studio_backend` directo (sin la GUI) y llama
`cnc_set({'material': {'thickness': 7}})`:

| | Código original | Con el arreglo |
|---|---|---|
| `cnc_set` | `ok: False` — `'charmap' codec can't encode character '″'...` | `ok: True` |
| `cnc_config.json` | 0 bytes | contenido completo |
| `cnc_get()` tras "reabrir" | 15.0 (default, silencioso) | 7.0 (persiste) |

Se reprodujo con `git stash` (código viejo) y se re-probó tras `git stash pop` (código arreglado) —
mismo mensaje de error predicho antes de correrlo, confirmando la causa con precisión.

Luego se **reconstruyó e instaló** la app (`DesignStudio.exe`) en esta Windows para validar
end-to-end, y se **reparó a mano** el `cnc_config.json` real de esta máquina (estaba en 0 bytes
desde antes) llamando al backend arreglado contra esa ruta real.

## Bonus: bug nuevo encontrado y arreglado en el camino

Al escribir `version.txt` con PowerShell (`Out-File -Encoding utf8`) se coló un **BOM UTF-8**
(`EF BB BF`) al inicio del archivo — `Out-File -Encoding utf8` en PowerShell 5.1 SIEMPRE agrega BOM.
`--diagnostico` no lo limpia al leer la versión y revienta con el mismo tipo de error
(`UnicodeEncodeError` en `cp1252`, esta vez con `﻿`). Si vuelves a escribir `version.txt` a
mano en Windows, usa algo que NO agregue BOM (`printf` en bash, o `[System.IO.File]::WriteAllText`
en PowerShell) — nunca `Out-File -Encoding utf8`. **`version.txt` en el repo es `"dev"`**; la
versión real solo se escribe en el pipeline de CI al publicar un release, nunca se commitea.

## Lección que rige esta sesión

**Medir en la máquina que falla, no deducir desde la que funciona** — la causa era 100% específica
de Windows (codepage cp1252 vs. default UTF-8 en Mac) y nunca iba a aparecer en las pruebas del Mac
sin importar cuántas veces se repitieran.

## Cierre de la clase entera — COMMIT `8c0e3bc`, release `v2026.07.29.6`

El arreglo tapó `studio_backend.py`, pero la **misma bomba seguía en otros cinco sitios**, con la
misma asimetría: se escribía en UTF-8 y se leía con el codepage del sistema.

| Sitio | Qué pasaba en Windows |
|---|---|
| `design_studio.py:87` · `studio_server.py:40` | Leían `plotter_config.json` sin `encoding` → área de trabajo silenciosamente a 3000×600 |
| `plotter_control.py:88` · `updater.py:50` | `version.txt` → ahora **`utf-8-sig`**, que además **se come el BOM** |
| `plotter_control.py:3840` y `:3859` | La config que **comparten las dos apps**, lectura y escritura |

- ⚠️ El de `updater.py` era el más grave: `.strip()` **NO quita el BOM**, así que la versión salía
  como `﻿2026.07.29.5` y **`vkey()` no podía compararla** — la auto-actualización decidiendo mal.
- **`utf-8-sig` en vez de una advertencia**: la nota decía "no escribas `version.txt` con
  `Out-File`", o sea confiaba en que nadie se equivoque. Con `utf-8-sig` **el código aguanta el BOM
  aunque aparezca**. Advertir no es arreglar.
- **NO se tocaron el `.tap` ni el HPGL**: escriben solo números (`G00 X%s Y%s`), sin texto del
  usuario, así que no pueden fallar. `tools_export` ya llevaba su `encoding`.
- ⚠️ **La regla está en `CLAUDE.md`**, no solo aquí: la memoria se lee bajo demanda, y esto es un
  "nunca hagas X" que basta un `write_text(json.dumps(...))` para reintroducir.

Verificado 6/6: cp1252 falla de verdad con `'Fresa 3.175 mm (1/8″)'`; `version.txt` **con BOM** se
lee limpio en ambas apps y `vkey()` da `(2026,7,29,5)`. Las 24 pruebas del actualizador, intactas.
