---
name: rebaba-microsegmentos
description: Por qué el .tap de Design Studio deja rebaba y el de Aspire no — RONDA 1 micro-segmentos del offset (3-ago-2026) y RONDA 2 avance irreal, pasada al doble y rampa al avance de corte (29-ago-2026)
metadata: 
  node_type: memory
  type: project
  originSessionId: 87a314c6-5428-4c70-a10b-0b8e43cd5e7b
  modified: 2026-08-04T21:48:04.623Z
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

✅ **ENCADENADO DE ANILLOS — HECHO** (3-ago-2026). `_chain_rings()` une anillos contiguos del
cajeado con un movimiento corto a profundidad de corte en vez de retirarse. Sobre el diseño real:
**67 → 5 trayectorias**, **68 → 9 retiros**, aire 6.90 → 5.06 m, y el recorrido de corte incluso
BAJA (78.0 → 76.4 m) porque desaparecen 60 rampas de entrada.

**La condición de unión es de SEGURIDAD:** solo se une si el tramo recto cabe dentro de
`poly.buffer(-radio)`. Con un cajeado partido en ISLAS, unirlas en recta arruina la pieza.

Detalles que costaron encontrar (todos en `CLAUDE.md`):
- `covers`, no `contains`: el anillo exterior va JUSTO sobre el borde de la zona y `contains`
  da falso para un punto del borde.
- Una cadena es un trayecto **ABIERTO** → necesitó `_open_pass` aparte, porque `_ring_pass`
  envuelve con `s % perim` y en un trayecto abierto saltaría del final al principio cortando.
- **Entre pasadas de profundidad hay que subir y volver al inicio por el aire.** Sin eso, la
  fresa cortaría en línea recta del extremo lejano al principio de la cadena.
- Primera versión: exigía que los anillos fueran CONSECUTIVOS y con islas no encadenaba nunca
  (36 → 36), porque los anillos vienen intercalados entre islas. Ahora busca más allá del
  siguiente, prefiriendo el más temprano (así dentro de cada isla sigue yendo de dentro afuera).

## El cajeado nuevo, medido contra el de Aspire (4-ago-2026)

Comparados sobre **la misma zona**: se reconstruyó el área del recorrido real (los tramos
engordados el radio de la fresa **son** el material retirado), dando 185 cm² contra los 182 cm²
de Aspire — 1.3 % de diferencia, así que la comparación vale. El paso lateral efectivo también
coincide (2.97 mm contra 2.91), o sea que barren con la misma densidad.

**A un mismo nivel de profundidad:**

| | Trayectorias | Corte | Aire |
|---|---|---|---|
| Aspire | 12 | 6.36 m | 1.06 m |
| DS código viejo | 44 | 6.14 m | 4.58 m |
| **DS código NUEVO** | **9** | 6.23 m | **0.88 m** |

**El cajeado nuevo ya GANA a Aspire**: menos trayectorias y menos aire recorriendo lo mismo.
El margen de aire que quedaba se agotó — las 9 cadenas están separadas por saltos largos de
verdad.

⏳ **Lo único que falta es un AJUSTE DE JOSE, no código:** Aspire hace el cajeado en UNA pasada
de 6 mm; DS lo parte en dos porque su preset tiene la **pasada máxima en 5 mm**. Poniéndola en
6 mm sería una sola pasada: **1.7 min contra los 6.4 de Aspire**. Se dejó a su criterio a
propósito — 6 mm de profundidad con fresa de 6 mm es **un diámetro completo de un tirón**, y
Aspire lo hacía a 1016 mm/min mientras él iría a 4000. Sugerido: probar primero con las dos
pasadas de 3 mm (3.3 min, ya la mitad que Aspire) y subir solo si la máquina va sobrada.

## "Última pasada separada": cómo funciona y su trampa (4-ago-2026)

Casilla en el panel de Perfil, con "Deja _ mm" e "Invertir dir.". El desbaste corta dejando una
**cáscara** (0.3–0.5 mm típico) y un **anillo aparte** la quita a medida exacta **en UNA pasada a
profundidad completa**. Ataca una causa de rebaba **distinta** a la de los micro-segmentos: con
poca mordida la fresa **no se flexiona**, y el borde no sale ondulado. En el perfil de 12.2 mm
cuesta **+50 % de recorrido** (6.26 → 9.39 m).

⚠️ **La trampa:** ese anillo va a fondo de una vez, y **sin entrada en rampa entra con un `G01 Z`
vertical** — medido, **17.20 mm de bajada de un tirón**, 12.2 de ellos dentro del material. Una
fresa de 2 filos no está hecha para taladrar: quema, puede agarrar y se maltrata. Con rampa la
bajada vertical más honda queda en **5.00 mm** (el aire hasta la superficie).

✅ **Arreglado** (COMMIT c7c79c0, release `v2026.08.04`): marcar la casilla **enciende solas** la
entrada en rampa e "Invertir dir.". Es un valor por DEFECTO, no una imposición — solo se tocan al
ENCENDER, y si Jose las apaga a mano se respetan.

⚠️ **Reserva dicha a Jose:** de las dos, la rampa es de seguridad y no tiene discusión, pero
**"Invertir dir." es experimental** — en la mayoría de los CAM la pasada de acabado va en el MISMO
sentido (concordante); invertirla es un truco para fibra levantada en triplay. Si al cortar sale
mejor sin invertir, es una línea.

**Orden recomendado a Jose para la rebaba** (importa, son causas distintas): 1) cortar el A/B con
la geometría ya limpia; 2) si aún queda, activar la última pasada; 3) fresa de compresión. La
última pasada **no sustituye** al arreglo de geometría: si el recorrido tartamudea, el anillo de
acabado tartamudea igual.

## Releases publicados

`v2026.08.03` (micro-segmentos) · `v2026.08.03.2` (zoom 3D al cursor + pasadas parejas +
encadenado del cajeado) · `v2026.08.04` (la última pasada enciende sola la rampa).

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

---

# RONDA 2 — 29-ago-2026: seguía habiendo rebaba, y ya no era la geometría

Jose cortó el **cocodrilo** (`Vetta Mirror/Espejos para niños/Animales/Cocodrilo/`) con los dos
programas: **una décima parte de rebaba** con Aspire, y "movimientos menos bruscos". Comparé
`cocodrilo.tap` (Vectric) contra `cocodrilo dstudio.tap`.

**Lo primero fue descartar la ronda 1: el arreglo de ago-2026 aguanta.** Segmentos más cortos
que 0.2 mm: **Aspire 14.0 %, nosotros 1.2 %** — nuestra geometría ya es *más limpia* que la suya.
La rebaba venía de tres cosas nuevas.

## 1. Le pedíamos un avance que la máquina no puede dar (la grave)

Aspire pide **F1270**, nosotros **F4000**. Para llegar a 4000 mm/min la máquina necesita
**3.7–11 mm solo de aceleración** (según su `a`, 200–1000 mm/s²), y el segmento típico de este
diseño mide **0.69 mm**: nunca llega. Simulé el perfil trapezoidal con look-ahead sobre el rango
entero de aceleración —**la conclusión no depende de saber la `a` real**:

| | Aspire | Design Studio |
|---|---|---|
| avance pedido | 1270 | 4000 |
| avance **real** logrado | ~667 | ~765 |
| **% del recorrido a velocidad ESTABLE** | **42.7 %** | **5.9 %** |

El 94 % del recorrido acelerando o frenando *es* "movimientos bruscos": el bocado de cada filo
oscila corte a corte. Y el F4000 **no compra nada** — misma geometría, solo cambiando el avance
pedido: F1270 → 13.02 min, F4000 → 12.20 min. **48 segundos**, a cambio de 6.5× menos estabilidad.

## 2. Bajábamos al doble y medio por pasada

Aspire: **5 pasadas de 2.44 mm**. Nosotros: **2 de 6.10 mm** = **1.02 × el diámetro** de la fresa
(todo el filo enterrado a la vez), **7× la fuerza de corte pedida**. La fresa se flexiona y rebota:
causa de rebaba **distinta** de la vibración.

⚠️ **CORREGIDO el 29-ago (yo lo había atribuido mal).** Primero dije que Jose había subido la
pasada de la biblioteca siguiendo un consejo mío de agosto. **Falso**: su biblioteca sigue en
`pass_depth = 5.0` para MDF (verificado en `cnc_config.json`), que daría `ceil(12.2/5) = 3`
pasadas de 4.07 mm. Los 6.10 mm salen del campo **"Pasadas" del formulario de la operación,
puesto en 2** — `effPassDepth()` en `studio_ui.html` devuelve `profundidad/N` cuando escribes
un N distinto del automático, y **ese campo le GANA a la biblioteca**. Consecuencia práctica:
cambiar la pasada de la biblioteca **no arregla nada** mientras el trabajo tenga el N forzado.
**Lección: antes de culpar a una configuración, comprueba cuál de los dos sitios que la fijan
está mandando** — aquí la evidencia estaba en el archivo (12.2/2 = 6.1 exacto, imposible con
pass_depth 5.0).

## 3. Entrábamos al material 7× más rápido (bug nuestro)

`_contour_body` emitía la rampa de entrada con `feed` en vez de `plunge`. Velocidad **vertical**
de entrada: **mediana 686 mm/min y picos de 2499**, contra los **90/381** de Aspire.

## Lo que se arregló en el código (29-ago-2026)

- **`_emit_cut()`**: todo movimiento que baja entrando al material va al avance de **picada**,
  decidido **por segmento**. Verificado en los 3 tipos de rampa: 0 entradas al avance de corte,
  vertical de 174 mm/min (antes 686).
- **`_modal()`**: salida modal como el post de Vectric (`G01`/`F` solo cuando cambian, ejes que no
  cambian omitidos) y **borrado de los 36 movimientos de largo cero**. De **32.3 a 17.6 caracteres
  por bloque** (Aspire: 17.1). Probado **ida y vuelta sobre el .tap real del cocodrilo**: mismos
  8816 movimientos, **desviación 0.000000000 mm**, 0 avances distintos.
- **`parseTap()` de la vista 3D**: descartaba las líneas sin `G` inicial → con la salida modal
  **veía 68 movimientos de 8812**, vista 3D casi vacía y **sin ningún error**. Arreglado y probado
  en node con el `parseTap` real sobre los dos formatos.
- **`auditar_gcode.py`**: parser modal + dos invariantes nuevos (nada de largo cero; todo lo que
  baja al material va a `plunge`). **133 verificaciones OK.**

## Lo que NO se tocó, y por qué

Los **presets** son la causa dominante y **son datos vivos de Jose**: no se cambian desde el
escritorio sin cortar. Recomendado para 6 mm / 2 filos en triplay: **avance 1500, bajada 400**
(biblioteca de fresas, por material) y **"Pasadas" = 5** en cada trayectoria de 12.2 mm — que es
el campo que de verdad manda. ⏳ **PENDIENTE: que Jose corte el A/B.** Nadie ha probado todavía
en la madera que esto sea lo que era.

## Lección de la ronda 2

**Compara el avance PEDIDO contra la distancia que hay para acelerar** (`v²/2a`). Si el segmento
típico es más corto que esa distancia, el número del archivo no lo va a ver nadie y la máquina va
a ir a tirones. Es la ronda 1 vista por el otro lado: entonces sobraban segmentos para la
velocidad, ahora sobra velocidad para los segmentos — **el mismo choque entre lo que el archivo
pide y lo que el control alcanza a ejecutar**.

Y una de método: **al cambiar el FORMATO de un archivo, busca a todos los que lo leen.** El
`.tap` tenía un segundo lector (la vista 3D) que se habría roto en silencio.

Relacionado: [[cnc-richauto]] (la integración y los presets), [[design-studio]],
[[render-3d-fidelidad]] (la vista 3D es fiel al recorte y ciega al terminado — no habría enseñado
nada de esto).
