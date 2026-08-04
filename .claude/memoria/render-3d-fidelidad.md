---
name: render-3d-fidelidad
description: "Qué puede y qué NO puede enseñarte la vista 3D del CNC — es fiel al recorte, ciega al terminado"
metadata: 
  node_type: memory
  type: project
  originSessionId: 87a314c6-5428-4c70-a10b-0b8e43cd5e7b
  modified: 2026-08-04T21:48:28.567Z
---

# La vista 3D: fiel al recorte, ciega al terminado

**4-ago-2026.** Jose preguntó si la vista 3D y la animación reflejarían los cambios en el corte y
el acabado. Verificado leyendo el circuito y midiendo, no de memoria. La respuesta tiene **dos
mitades opuestas** y conviene tenerlas claras antes de confiar en lo que se ve.

## Al RECORTE: sí, es fiel

La simulación **no recalcula nada por su cuenta**. Pide al backend el `.tap` real —por el mismo
camino que la exportación— y lo interpreta línea por línea:

```js
simTap(...).then(r => jobs.push({ moves: parseTap(r.tap), rad: dia/2 }))
```

`parseTap` lee los G00/G01 tal cual y `stampMove` estampa la fresa como **cilindro del radio real**
sobre un mapa de alturas. En el diseño de Jose la rejilla salió de **1549×1549 = 2.4 M celdas, de
0.25 mm cada una** (`cell = max(0.15, sqrt(W*H/2.4e6))`, adaptativa al tamaño de lo que se corta).

Por tanto **sí** refleja: profundidades, número de pasadas, orden de corte, encadenado, pasantes,
y mordidas a la cama (las pinta en rojo).

## Al TERMINADO: no, y no puede

Es un **mapa de alturas**: pura geometría. No modela vibración, rebaba, quemado ni desgarro de
chapa — eso depende de avance, RPM, fresa y material, no de la forma.

**Medido, no supuesto:** simulado el cajeado ANTES y DESPUÉS de los arreglos del 3-ago
(reparto de pasadas + encadenado):

```
celdas que difieren: 0 de 2 399 401   (0.0000 %)
diferencia de altura máxima: 0.0000 mm
```

**Cero.** Buena noticia por un lado —confirma que los cambios no alteran la pieza— pero significa
que **la vista 3D se ve exactamente igual que antes**.

Lo mismo con los micro-segmentos que causaban la rebaba ([[rebaba-microsegmentos]]): el segmento
culpable medía **0.047 mm = 0.18 de una celda**. Ni en principio se puede ver. Al comparar el
`.tap` original con el limpio salieron 165 celdas distintas de 2.4 M, y se comprobó que son
**discretización del borde** (la previsión matemática daba 329, del mismo orden), no rebaba.

⚠️ **Dicho claro: la vista 3D no habría enseñado el problema de la rebaba, ni enseña la mejora.**

## Para qué SÍ sirve

- **Verificar el encadenado del cajeado.** Una unión mal hecha cortaría un canal de 6 mm de ancho
  por donde no debe — cientos de celdas, **se ve a simple vista**. Es el mejor segundo par de ojos
  para el riesgo que introdujo `_chain_rings`.
- **La animación sí refleja el cambio de ruta**: repasa los mismos movimientos, así que se ve la
  fresa levantarse 9 veces en vez de 68.
- Orden de corte (que las piezas no se suelten antes de tiempo), profundidades, pasantes.

**Límite de resolución: ~0.25 mm.** Cualquier detalle por debajo de medio milímetro no es de fiar.

## Lección (señal)

**Una simulación geométrica solo puede fallar en geometría.** Antes de usar una vista 3D para
juzgar algo, pregunta qué magnitud física modela: un mapa de alturas responde "¿qué forma queda?",
nunca "¿cómo queda la superficie?". Si el problema es de acabado, la respuesta está en la pieza,
no en la pantalla.

Relacionado: [[rebaba-microsegmentos]] (el problema que esta vista no podía ver),
[[cnc-richauto]], [[design-studio]].
