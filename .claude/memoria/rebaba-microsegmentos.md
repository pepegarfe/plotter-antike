---
name: rebaba-microsegmentos
description: Por qué el .tap de Design Studio dejaba rebaba y el de Aspire no — micro-segmentos del offset de shapely (RESUELTO 3-ago-2026)
metadata: 
  node_type: memory
  type: project
  originSessionId: 87a314c6-5428-4c70-a10b-0b8e43cd5e7b
  modified: 2026-08-03T22:40:02.407Z
---

# La rebaba del CNC eran micro-segmentos, no la velocidad

**3-ago-2026.** Jose cortó la MISMA pieza (marco ondulado circular, triplay 12 mm, fresa 6 mm de
2 filos) con dos archivos: uno de **Aspire** y uno de **Design Studio**. El de Aspire salió mucho
más limpio; el de Design Studio, con rebaba — aunque Aspire tardó **más del triple**.

## Qué NO era (todo verificado midiendo los dos .tap)

El perfil de los dos archivos es **geométricamente idéntico**: mismos perímetros (923.9 y
1212.6 mm), mismas 2 pasadas (Z −6.10 y −12.20, escalón de 6.1 mm), mismos sentidos de giro, sin
puentes en ninguno. Ninguna de las sospechas habituales explicaba nada.

## Qué SÍ era

`cnc_gcode.py` compensaba la fresa con `region.buffer(..., quad_segs=16)` de shapely **y nadie
limpiaba el resultado**. `buffer()` redondea CADA vértice con un arco: con los giros suaves de un
contorno ondulado (~0.9°), ese arco mide `3 mm × 0.9° ≈ 0.047 mm`. Resultado: un
**micro-segmento pegado a cada segmento bueno**, en patrón largo-corto-largo-corto.

Medido en el archivo de Jose: **1142 de 1167 movimientos** del contorno grande alternaban así;
**48.7 %** de los segmentos por debajo de 0.05 mm. En el de Aspire, 6 y 7 saltos en total.

**Por qué arruina la madera:** a 4000 mm/min un movimiento de 0.04 mm dura **medio milisegundo**.
El control RichAuto no puede ejecutarlo, así que frena. Como el patrón se repite cada dos
movimientos, la máquina entra en frena-acelera a ~60 golpes por segundo → vibración, y el bocado
de cada filo oscila entre casi cero (frota y quema) y 0.11 mm (muerde fuerte). **Ese vaivén es lo
que desgarra la chapa del triplay.** Aspire corría al 93–98 % de su avance programado: parejo.

⚠️ **La vuelta de tuerca contraintuitiva:** en el papel los números de Design Studio eran los
CORRECTOS (0.111 mm por filo, dentro de lo recomendado 0.08–0.13); Aspire iba *por debajo* de lo
ideal (0.032 mm, casi frotando) **y aun así ganó**. Un bocado constante y modesto vence a uno
ideal pero errático. La regularidad importa más que el número.

## El arreglo

`_simplify()` en `cnc_gcode.py` (Douglas-Peucker a `_SIMPLIFY_MM` = 0.01 mm), aplicado en los
**tres** sitios donde la geometría desplazada se vuelve puntos: `_units_from()` (perfil),
`_rings_flat()` (cajeado) y `_offset_side()` (izquierda/derecha). **La regla vive en `CLAUDE.md`**,
no solo aquí.

Medido sobre el DXF real por el pipeline de la app: perfil **989 micro-segmentos → 0**, mitad de
puntos, el perímetro cambia **0.03 mm (0.0009 %)**. `auditar_gcode.py`: **133 verificaciones OK**.

## Estado / pendiente

Se dejó un `.tap` para corte A/B junto al original (Google Drive → …/Ondulado circular/
`Ondulado circular 38cm LIMPIO.tap`). **No se regeneró desde el DXF a propósito**: se limpió el
archivo YA cortado, así el A/B tiene **una sola variable** (la densidad de puntos) — mismo orden,
profundidades, rampas y avances. Verificado subconjunto exacto del original, desviación máxima
real **0.00999 mm**.

⏳ **PENDIENTE: que Jose corte el A/B.** El diagnóstico está medido sobre la geometría, pero
**nadie ha probado que la máquina tartamudeara** — eso solo lo confirma el corte.

También pendiente de decidir tras el A/B: si F4000 sigue siendo demasiado (con la geometría limpia
el modelo estima que la máquina promedia ~1800–2350 mm/min, aunque ese modelo ignora el
look-ahead y es pesimista), y probar la **fresa de compresión** (`t6-comp`, ya configurada), que es
lo que el triplay pide para que no se levante la chapa de arriba.

## Comparación de RUTA entre los dos .tap (3-ago-2026, a petición de Jose)

Medido el recorrido completo de los dos archivos. **El perfil coincide al centímetro**
(2.14 m a −6.10 y 2.14 m a −12.20 en AMBOS). Toda la diferencia está en el cajeado:

| | Aspire | Design Studio |
|---|---|---|
| Cortando de verdad | 10.41 m | **16.41 m** (×1.58) |
| En aire (G00) | 1.92 m | 5.02 m (×2.6) |
| Subidas a seguridad | 16 | 51 (×3.2) |
| Entrando en rampa | 0.25 m | 1.48 m (×6) |
| Tiempo total | 11.82 min | 5.56 min |

**Los 6 m de más son una pasada de cajeado entera**: Aspire lo hace en UNA pasada de 6 mm;
Design Studio en dos (5 mm + **1 mm**) por culpa de `_passes()`. ✅ **ARREGLADO** (reparto
equitativo → 3+3). Ojo: **no ahorra distancia** (mismo recorrido), quita el raspado.

Lo demás, en contexto: el aire cuesta solo 0.63 de los 5.56 min (11 %), y las rampas largas de
DS (34.6 mm vs 6 mm) son **mejores** para la fresa que el casi-clavado de Aspire. La altura de
retirada de DS (siempre 5 mm) también es mejor que la de Aspire (sube a 20 mm varias veces).

⚠️ **Autocorrección al medir:** la primera cifra de "desorden del aire" (55 % de margen) estaba
**inflada** — reordenaba libremente entre los 6 trabajos del archivo, cosa imposible sin
fusionarlos. Trabajo por trabajo el margen real es 29 %, y aun ese es un **techo**, porque el
cajeado debe ir del centro a la pared en cada zona. **Al medir una optimización, comprueba que el
"ideal" con el que comparas sea alcanzable.**

⏳ **PENDIENTE (decidido aparte, no hecho):** encadenar anillos contiguos del cajeado en vez de
retirarse entre cada uno. Aspire hace el cajeado en **12 trayectorias** y DS en **49**; Aspire
encadena algunos anillos (2 saltos < 5 mm), DS **ninguno** (su salto más corto es de 32 mm).
Ahí está el ahorro de aire real.

## Lecciones (señales)

- **Dos archivos, misma geometría, uno vibra → compara el LARGO DE LOS MOVIMIENTOS**, no las
  trayectorias. Largo-corto-largo-corto = geometría de computadora sin limpiar.
- **Cuidado con el reflejo de "bajarle la velocidad":** aquí la velocidad no era la causa, era el
  síntoma de que la máquina no podía sostenerla.
- **Al medir, desconfía de tu propia herramienta.** Mi primera medición de desviación dio 0.92 mm
  (inaceptable) y era un artefacto de una ventana deslizante que perdía el paso al haber la mitad
  de puntos. La medición correcta —el archivo limpio es un *subconjunto ordenado* del original, así
  que cada punto quitado se compara contra el segmento que lo sustituye— dio 0.00999 mm.
- **Al post-procesar G-code, emite las líneas ORIGINALES tal cual.** Al reescribirlas yo convertí
  `G01 Z7 F24` (solo Z) en `G01 X0 Y0 Z7 F24`, que ordena un movimiento en XY que el original no
  pedía. Una línea que OMITE un eje depende del valor modal anterior: si quitas el punto de antes,
  hereda una posición equivocada.

Relacionado: [[cnc-richauto]] (la integración y los presets), [[design-studio]].
