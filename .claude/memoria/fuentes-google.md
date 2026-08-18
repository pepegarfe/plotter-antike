---
name: fuentes-google
description: Cómo se agregan tipografías (se instalan en el SO, no en la app), la instalación curada de Google Fonts de ago-2026 y por qué el selector se agrupó por familia.
metadata:
  type: project
---

# Tipografías: de dónde salen y el catálogo de Google Fonts

**18-ago-2026.** Design Studio **no tiene carpeta propia de fuentes**: `text_vector.list_fonts()`
recorre las carpetas del sistema (`_font_dirs()`) con fontTools, se queda solo con las que tienen
**alfabeto latino** (`_usable`: exige `A` y `a` en el cmap) y guarda `fonts_cache.json`. Agregar una
tipografía = instalarla en el sistema operativo; la app la ve al reabrir, porque el caché se
invalida con una firma de esas carpetas (`_dirs_sig`: fecha + nº de archivos). **Esa firma solo mira
el primer nivel** → fuentes metidas en una subcarpeta preexistente pueden pasar desapercibidas.

## Lo que se instaló (Mac de Jose)

Se bajaron las **200 familias más populares** de Google Fonts que aún NO estaban en la Mac (140 ya
estaban), en Regular/Bold y sus itálicas, vía la API `css2` con **User-Agent viejo** — el truco que
hace que Google sirva `.ttf` en vez de `.woff2`, que la app no lee. **556 archivos, 117 MB**,
copiados sueltos a `~/Library/Fonts` sin sobrescribir nada; la lista para desinstalar quedó en
`~/Library/Fonts/google-fonts-instaladas.txt`. Resultado medido: **413 → 969 fuentes (343 familias)**,
escaneo completo 4.7 s (igual que antes) y 0.001 s con caché. Las 556 pasan el criterio del propio
programa y `text_paths` genera trazos correctos (Bebas Neue, "ANTIKE": 7 contornos, alto de
mayúsculas 20.00 mm exactos).

**Por qué NO se instaló el catálogo entero** (1,942 familias / 7,478 archivos / 1.3 GB): 461 familias
"Display" y 254 manuscritas tienen trazos capilares que en vinil se desgarran, y una lista de miles
de nombres hace más difícil encontrar la que se busca, no más fácil. El límite real no es el disco.

## El selector: agrupado por familia y dibujado por tandas

El desplegable pintaba **una fila por archivo de fuente**, y cada fila se dibuja **con su propia
tipografía** (esa es la gracia). Eso obliga al motor web a cargar tantas tipografías como filas cada
vez que se abre el menú: con 413 no se nota, con miles sí. Ahora (`studio_ui.html`) hay **una fila
por familia** — los pesos aparecen adentro al abrirla, o solos si buscas "oswald bold" — y solo se
dibujan ~60 filas, pidiendo más al llegar al fondo. Verificado con el JS REAL del archivo corriendo
en node sobre un DOM falso: **20 checks** con un catálogo inventado de 3,600 fuentes y **7 más** con
el catálogo real de la Mac.

**Lección:** el costo de una lista no siempre está en cuántos elementos hay, sino en **qué recurso
carga cada elemento**. Una fila de texto es gratis; una fila que estrena tipografía, no. Ver
[[design-studio]] y [[estado]].
