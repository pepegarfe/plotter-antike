---
name: idea-web-online
description: Idea guardada — Design Studio como app web local multi-dispositivo (prototipo funcional, en pausa)
metadata:
  type: project
---

# Idea: Design Studio "online" (app web local) — EN PAUSA

Explorada el 21-jul-2026 y **pausada por decisión de Jose** para seguir con la plataforma real.
Se guarda porque el prototipo **funciona** y quizá se retome.

## Qué quería Jose
Abrir Design Studio **desde varios dispositivos** (laptop, tablet, teléfono) y **sin instalar nada**.

## La arquitectura que lo cumple
Un **servidor web local** que corre en la Mac conectada al plotter. Otros dispositivos en la
**misma red WiFi** abren el navegador en `http://<ip-de-la-mac>:8765` y usan la app sin instalar nada.
La cara (HTML/CSS/JS) es la misma que la de escritorio; solo cambia el transporte (pywebview → HTTP).

- **`studio_server.py`** — servidor con `bottle` (ya instalado). Sirve `studio_ui.html` y expone
  `GET /api/workarea` y `POST /api/parse` (sube un archivo → lo parsea con el motor → devuelve
  trazados en mm + bbox). **Probado y funcionando** (leyó `prueba-corte.svg`: 7 trazados, bbox ok).
- La versión de escritorio equivalente es **`design_studio.py`** (pywebview), misma `studio_ui.html`.
  ⚠️ Ojo: `studio_ui.html` quedó adaptado a **fetch/HTTP** (modo servidor). Para volver a pywebview
  hay que regresar la parte de "Abrir" al puente `window.pywebview.api` (o hacerlo dual).

## El candado honesto (por qué NO es "puro online")
Cortar necesita el **USB del plotter**, y un navegador **no puede** tocar el puerto serie de la
máquina. Por eso:
- La Mac conectada al plotter es la que **sirve** la app y hace los cortes; los demás dispositivos
  son "estaciones de diseño" remotas.
- Entrar **desde fuera de la red local** (internet abierto) necesita un paso extra (túnel/exponer el
  puerto, con cuidado de seguridad). En pausa.

## Estado
Prototipo web funcional en `studio_server.py` + `studio_ui.html`. Se retoma si Jose quiere el acceso
multi-dispositivo. Relacionado: [[estado]].
