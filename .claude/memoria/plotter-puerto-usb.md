---
name: plotter-puerto-usb
description: El plotter se ve como FTDI FT232R (/dev/cu.usbserial-…) y el orden correcto para diagnosticar cuando "no aparece"; por qué la lista de puertos ahora trae nombres legibles.
metadata:
  type: project
---

# Cuando el plotter "no aparece": primero pregúntale al sistema, no al programa

**18-ago-2026.** El plotter de corte se conecta por un **FTDI FT232R**, chip con soporte
de fábrica en macOS: **no hay driver que instalar**. En la Mac de Jose se ve como
`/dev/cu.usbserial-AO004NFH` (`AO004NFH` es el número de serie del chip, así que el nombre
es estable en esa máquina). Velocidad guardada: 9600.

## El orden de diagnóstico (lo que costó media hora)

Cuando el programa "no lo detecta", la primera pregunta **no** es si falla la app:

1. **¿Lo ve el sistema operativo?** `ioreg -p IOUSB -w0` (árbol USB) y `ls /dev/cu.*`.
   Si el árbol solo muestra los controladores del Mac, **no hay nada enchufado** — ni el
   plotter ni el adaptador. Ese día pasó justo eso: nada a las 19:41, y al reconectar el
   cable apareció `FT232R USB UART` a las **19:42:49**. Era contacto del cable, no software.
   Truco: dejar un vigía de 90 s muestreando cada 2 s mientras se reconecta; la **hora exacta**
   de aparición prueba la relación causa-efecto que "ya lo probé" no prueba.
2. **Si el sistema lo ve pero el programa no**: la lista de puertos se leyó al abrir la app,
   antes de que existiera el puerto → **refrescar** (el botón junto al desplegable).
3. **Si el sistema ve el aparato USB pero no aparece ningún `/dev/cu.usbserial-…`**: ESO sí
   es driver (CH340, CP210x, Prolific). No fue el caso aquí.

**Lección general:** un fallo "del programa" que en realidad vive dos capas más abajo se
delata pidiendo evidencia al nivel más bajo primero. Y ojo con la trampa contraria: la
`config` guardada tenía el puerto `/dev/cu.debug-console`, un aparato **interno** del Mac —
o sea que la lista cruda invitaba a elegir mal.

## Lo que se cambió a raíz de esto (COMMITS 41afada, fa2b5c9)

- **Nombres legibles** en el desplegable: `Cable USB — FT232R USB UART` en vez de la ruta.
  ⚠️ El **valor** de cada opción sigue siendo la ruta real: cambia lo que se ve, no lo que
  se envía.
- **Dos grupos: "Cables USB" y "Otros"**, separados por el **VID/PID**: solo los cables USB
  de verdad lo traen; Bluetooth, audífonos emparejados y la consola de depuración vienen
  vacíos y **nunca** son un plotter. Es una regla física, no una lista de nombres.
- **Un solo cable USB y sin memoria previa → queda elegido solo.**
- **Recuerda el último puerto y velocidad que SÍ conectaron** (`plotter_prefs.json`, en el
  folder de config; archivo propio porque la app tkinter reescribe `plotter_config.json`
  con solo sus llaves). Una conexión fallida **no** se guarda.

---

# SEGUNDO EPISODIO — 2-sep-2026: esta vez SÍ era el programa, y no era detección

Jose: *"¿por qué el programa no está detectando el plotter? ya está conectado"*. El orden de
diagnóstico de agosto pasó los tres pasos **sin encontrar nada**:

| comprobación | resultado |
|---|---|
| ¿lo ve el sistema? | **sí** — `/dev/cu.usbserial-AO004NFH`, creado ese día 09:12 |
| ¿lo ve pyserial, en el intérprete que corre la app? | **sí** — Python 3.14.6, pyserial 3.5 |
| ¿lo arma bien `_port_items()`? | **sí** — primero de la lista, `Cable USB — FT232R USB UART` |

**No era detección: era PRESELECCIÓN.** `plotter_prefs.json` recordaba
`/dev/cu.Buds3ProdeJose` — **sus audífonos** — y en `refreshPorts` la memoria se evaluaba
ANTES que la autoselección del único cable:

```js
var cur = sel.value || pref || lastPort;                     // pref = los audifonos
if(cur && rutas.indexOf(cur)>=0){ sel.value=cur; return; }   // <- se salia AQUI
if(usb.length===1) sel.value=usb[0].port;                    // <- nunca llegaba
```

Como los audífonos **siguen existiendo** en la lista, ganaban siempre. El plotter estaba en
el desplegable, bajo "Cables USB", pero el que aparecía elegido era otro.

**Cómo llegaron ahí:** `_prefs_save()` guarda al conectar, y **abrir un puerto Bluetooth
SIEMPRE "funciona"** aunque no haya nada del otro lado — así que una conexión equivocada se
graba como si fuera buena. La guarda "una conexión fallida no se guarda" no sirve aquí:
*no falló*.

## El arreglo (`refreshPorts` en `studio_ui.html`)

Prioridad explícita, con el recordado **al final**:

1. el puerto **realmente conectado** (`connPort`) — no se lo quita nadie;
2. lo que el usuario eligió a mano en el panel (sobrevive a pulsar ↻);
3. **el único cable USB** — si solo hay uno, ese es el plotter;
4. el puerto recordado.

Probado en node con el `refreshPorts` real y un DOM falso, **8 casos, antes y después**: solo
cambian los dos que estaban mal (el de Jose, y "ya conectado", que también se dejaba pisar por
la memoria); los otros seis dan idéntico. La explicación vive **en un comentario dentro de la
propia función**, que es donde alguien la va a romper.

⚠️ **NO se tocó `plotter_control.py`** (la app tkinter): su `_refresh_ports` elige `ports[0]`
a ciegas, que en esta Mac sería la consola de depuración. No se distribuye desde jul-2026 y el
trabajo de puertos de agosto tampoco la tocó — queda anotado, no arreglado.

## Lección

El orden *sistema → refresco → driver* es bueno pero **incompleto**: da por hecho que el
síntoma es "no aparece". Cuando los tres pasos salen limpios, **deja de preguntar por qué no
aparece el que buscas y mira qué apareció en su lugar** — la respuesta estaba en un archivo de
una línea. Y como regla de diseño: **una preferencia recordada no debe ganarle a una señal
física del presente** (aquí, un VID/PID de cable USB real).

Ver [[design-studio]] y [[estado]].
