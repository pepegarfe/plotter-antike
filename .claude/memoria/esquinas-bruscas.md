---
name: esquinas-bruscas
description: "Por qué la CNC da tirones en las esquinas de 90°: solo pasa en perfil POR DENTRO y en CAJEADO (el perfil por fuera ya sale redondeado); diagnóstico medido 26-sep-2026"
metadata:
  node_type: memory
  type: project
  originSessionId: a8b5fe0c-1b18-4e26-96ab-c279cb3e809d
  modified: 2026-09-26T18:13:04.272Z
---

# Tirones en las esquinas de 90° (diagnóstico 26-sep-2026)

Jose: "los cambios de dirección se sienten muy bruscos, por ejemplo en ángulos de 90°".

**Medido sobre un cuadrado de 100 mm con fresa de 6 mm** (`make_toolpaths`/`make_pocket` reales):

| operación | giros > 30° en la trayectoria |
|---|---|
| perfil POR FUERA | **0** (giro máx 5.6°: `buffer()` redondea la esquina con el radio de la fresa) |
| perfil POR DENTRO | **4 de 90°** (esquina viva, geometría obligada) |
| CAJEADO | **100**: 90° en cada esquina de cada anillo **+ 45°/135° en cada enlace** de `_chain_rings` (el enlace va en diagonal y luego casi da media vuelta) |

El `.tap` real `PLANO 23-07` (perfil por fuera, F3600): 239 giros, todos < 10°. → Los tirones
salen de **perfiles por dentro y cajeados**, no del perfil por fuera.

**Por qué es físico, no un bug:** con solo G01 (sin arcos), en una esquina de 90° la velocidad en
X tiene que llegar a cero y la de Y arrancar de cero → el control **se detiene** en cada esquina.
La violencia del frenón la fijan (1) la **aceleración configurada en el handle** del RichAuto y
(2) el **avance pedido**: a F4000 (preset 6 mm/2 filos MDF, todavía sin cambiar) hay ~7× más
energía que matar que a F1500 en cada esquina.

**Palancas posibles (propuestas, ninguna aplicada todavía):**
- Cajeado: redondear las esquinas de los anillos INTERIORES (el último, el de la pared, sigue
  vivo) → gratis, no cambia la pieza; verificar cobertura con shapely antes de aceptar.
- Perfil por dentro: redondear la esquina SÍ cambia la pieza (la esquina interior queda con
  radio fresa+ρ) → solo como opción explícita.
- Presets / aceleración del handle: datos vivos de Jose, ver [[rebaba-microsegmentos]] (misma
  raíz: lo que el archivo pide contra lo que el control alcanza).

**Señal para la próxima vez:** antes de tocar nada, cuenta los giros > 30° por operación; si el
perfil por fuera no tiene ninguno, el problema vive en los interiores.
