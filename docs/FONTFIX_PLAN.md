# PSVitaAlive FONTFIX

> **Estado:** propuesta técnica documentada, **no implementada**.
>
> Este documento recoge el análisis del sistema actual de fuentes de PSVitaAlive y una propuesta de mejora futura para corregir inconsistencias visuales en fuentes `.ttf` / `.otf`, mantener compatibilidad con `.pgf` y conservar el selector de fuentes ya existente.

## 1. Objetivo

Mejorar el renderizado de fuentes personalizadas en el cliente de PS Vita para evitar problemas como:

- caracteres que parecen más grandes o más pequeños que otros dentro de una misma línea;
- diferencias de grosor o nitidez entre letras;
- fuentes TTF/OTF que a 100% se ven demasiado grandes o demasiado pequeñas;
- alineación vertical irregular respecto a la fuente PGF del sistema;
- caracteres faltantes cuando una fuente no cubre el idioma seleccionado;
- comportamiento distinto dependiendo del orden en que se hayan dibujado o medido los textos.

La solución debe conservar:

- fuentes incluidas dentro del VPK en `app0:font/`;
- fuentes añadidas por el usuario en `ux0:data/psvitaalive/fonts/`;
- soporte `.pgf`, `.ttf` y `.otf`;
- selector actual de fuente;
- ajuste global de tamaño 50%–150%;
- compatibilidad con los idiomas existentes;
- rendimiento y consumo de memoria adecuados para PS Vita real.

---

## 2. Implementación actual

El sistema de fuentes está centralizado principalmente en:

```text
Client PSVitaAlive/include/ui/ui_font.hpp
Client PSVitaAlive/source/ui/ui_font.cpp
```

Actualmente el cliente:

1. escanea:
   - `app0:font/`
   - `ux0:data/psvitaalive/fonts/`
2. acepta:
   - `.pgf`
   - `.ttf`
   - `.otf`
3. carga PGF con:

```cpp
vita2d_load_custom_pgf(...)
```

4. carga TTF/OTF con:

```cpp
vita2d_load_font_file(...)
```

5. encapsula ambas variantes dentro de `UiFont`.

Esto permite que la UI use funciones comunes:

```cpp
uiDrawText(...)
uiTextWidth(...)
```

sin necesitar saber si la fuente activa es PGF o FreeType.

Esta arquitectura debe conservarse porque permite corregir el problema de forma centralizada.

---

## 3. Conversión actual PGF -> FreeType

La interfaz original fue diseñada usando escalas PGF como:

```text
0.50
0.58
0.62
0.74
0.86
1.00
1.12
...
```

Para evitar modificar todos los puntos de dibujo de la UI, `ui_font.cpp` transforma esa escala histórica a un tamaño FreeType en píxeles mediante una función aproximada:

```cpp
px = 8 + scale * 13
```

El resultado se limita aproximadamente al rango 12–36 px y se redondea a tamaños pares.

La alineación vertical de FreeType también usa actualmente un pequeño desplazamiento fijo:

```cpp
yFt = y + 1 / y + 2
```

según el tamaño.

### Limitación

Dos archivos TTF configurados a 20 px no tienen necesariamente el mismo tamaño visual.

Cada fuente puede tener distintas métricas internas:

- ascender;
- descender;
- x-height;
- cap-height;
- line gap;
- unidades por em;
- hinting.

Por lo tanto, una conversión fija de escala PGF a píxeles no puede normalizar visualmente todas las fuentes.

Esto explica una parte de las diferencias de tamaño entre fuentes, pero no explica por sí solo las diferencias entre caracteres de una misma fuente.

---

## 4. Problema principal encontrado en libvita2d

PSVitaAlive utiliza FreeType mediante `libvita2d`.

El paquete actual de VitaSDK usa la implementación procedente de `xerpi/libvita2d`.

En la versión analizada, cada `vita2d_font` crea un atlas de glyphs de:

```text
512 x 512
```

La estructura del atlas guarda cada glyph utilizando únicamente su:

```text
glyph_index
```

como clave.

El tamaño de renderizado no forma parte de esa clave.

Conceptualmente, el comportamiento actual es:

```text
atlas[glyph_index] = glyph rasterizado
```

en vez de:

```text
atlas[glyph_index, pixel_size] = glyph rasterizado
```

### Ejemplo

Si una letra se utiliza primero a 24 px:

```text
A -> rasterizada a 24 px -> guardada en atlas
```

pero otra aparece primero en texto pequeño:

```text
e -> rasterizada a 16 px -> guardada en atlas
```

más adelante ambas pueden pedirse a 20 px.

libvita2d reutiliza el glyph que ya existe en el atlas y calcula un factor de escala similar a:

```cpp
draw_scale = requested_size / cached_glyph_size;
```

Por tanto:

```text
A@24 -> reducida para dibujarse a 20

e@16 -> ampliada para dibujarse a 20
```

Aunque ambas terminen ocupando aproximadamente el tamaño solicitado, han sido rasterizadas originalmente a tamaños distintos.

Esto puede producir diferencias de:

- nitidez;
- grosor;
- hinting;
- contorno;
- percepción del tamaño.

Este comportamiento coincide especialmente bien con el síntoma reportado de letras que parecen de tamaños distintos dentro de una misma fuente.

---

## 5. La medición de texto también puede afectar al atlas

`vita2d_font_text_dimensions()` utiliza internamente el mismo recorrido de glyphs que el renderizador.

Aunque se llame únicamente para medir un texto, puede provocar que un glyph sea rasterizado y almacenado en el atlas.

PSVitaAlive usa esta función desde:

```cpp
uiTextWidth(...)
```

Por tanto el primer tamaño almacenado para una letra no tiene por qué venir de un texto visible.

Ejemplo:

```text
1. La UI mide "Settings" a 16 px.
2. Los glyphs se almacenan a 16 px.
3. Más tarde "Settings" se dibuja como título a 24 px.
4. libvita2d reutiliza y escala los glyphs de 16 px.
```

Esto significa que el resultado visual puede depender del orden en que la aplicación haya medido o dibujado los textos desde el arranque.

---

## 6. Problema de cobertura Unicode

PSVitaAlive permite que el usuario copie cualquier `.ttf` / `.otf` compatible en:

```text
ux0:data/psvitaalive/fonts/
```

pero actualmente seleccionar una fuente no garantiza que esa fuente contenga todos los caracteres necesarios para el idioma activo.

Por ejemplo una fuente puede contener:

```text
Latin
Latin Extended
```

pero no:

```text
Cyrillic
Greek
CJK
```

Cuando FreeType no encuentra un carácter, el renderer termina utilizando el glyph faltante de la fuente.

Actualmente no existe una cadena de fallback automática por carácter.

### Limitación adicional de libvita2d

La función UTF-8 usada por la implementación actual de `libvita2d` decodifica secuencias de hasta tres bytes y trabaja esencialmente con UCS-2/BMP.

Esto significa que caracteres Unicode fuera del BMP, especialmente muchos emoji y símbolos modernos codificados con cuatro bytes UTF-8, no son manejados correctamente por esta ruta.

Esta limitación debe considerarse independiente de la cobertura de la propia TTF.

---

# 7. Estrategia recomendada

No se recomienda eliminar TTF/OTF ni obligar a los usuarios a convertir todas las fuentes a PGF.

Tampoco se recomienda empezar manteniendo un fork completo de `libvita2d`.

La solución preferida es mantener la abstracción `UiFont` y corregir el comportamiento dentro del cliente.

La propuesta se divide en fases independientes para poder validar cada una antes de continuar.

---

# FONTFIX-0 — Diagnóstico visual

## Objetivo

Confirmar el comportamiento en:

- Vita3K;
- PS Vita real.

## Cambios previstos

Añadir temporalmente instrumentación y/o una pantalla de prueba que permita comparar:

```text
ABCDEFGHIJKLM
abcdefghijklm
0123456789
ÁÉÍÓÚ ñ ç ß
Cyrillic
Greek
```

usando varios tamaños lógicos de la UI.

Registrar:

```text
font file
font kind
logical scale
user scale
final px
measured width
measured height
```

### Criterio de validación

Reproducir visualmente el problema y comprobar si cambia según el orden en que se dibujan los tamaños.

Esta fase no debe cambiar el comportamiento normal del usuario.

---

# FONTFIX-1 — FreeType separado por tamaño

## Objetivo

Eliminar el problema provocado por reutilizar un mismo atlas de `vita2d_font` para múltiples tamaños.

## Diseño

Actualmente:

```text
UiFont
 └── vita2d_font*
      ├── 14 px
      ├── 16 px
      ├── 18 px
      ├── 20 px
      ├── 22 px
      └── 24 px
```

La propuesta es:

```text
UiFont
 ├── FreeType instance 14 px
 ├── FreeType instance 16 px
 ├── FreeType instance 18 px
 ├── FreeType instance 20 px
 ├── FreeType instance 22 px
 └── FreeType instance 24 px
```

Cada instancia de `vita2d_font` se usaría exclusivamente para un tamaño lógico concreto.

Así, dentro de cada atlas:

```text
A = 18 px
B = 18 px
C = 18 px
...
```

Nunca se mezclarían glyphs inicialmente rasterizados a tamaños distintos.

## Importante

Tanto:

```cpp
uiDrawText(...)
```

como:

```cpp
uiTextWidth(...)
```

deben resolver exactamente la misma instancia correspondiente al tamaño solicitado.

## Caché recomendado

No es necesario cargar todas las instancias al iniciar.

Se propone un caché bajo demanda:

```text
requested px
    |
    +-- cache hit -> reutilizar instancia
    |
    +-- cache miss -> crear vita2d_font para ese tamaño
```

Puede añadirse un pequeño límite/LRU para evitar acumular demasiados atlas si en el futuro aparecen muchos tamaños diferentes.

## Memoria

El atlas actual de cada `vita2d_font` es 512x512 en formato de 8 bits, equivalente aproximadamente a 256 KiB de textura antes de considerar estructuras y alineación de memoria GPU.

Por este motivo debe evitarse crear indiscriminadamente decenas de instancias.

La UI actual ya tiende a reutilizar un conjunto relativamente pequeño de escalas, por lo que un caché limitado debería ser suficiente.

## Criterio de validación

- Las letras de una misma línea deben mantener grosor y nitidez consistentes.
- El resultado no debe cambiar dependiendo del orden en que se abran pantallas.
- `uiDrawText()` y `uiTextWidth()` deben coincidir.
- No debe haber regresiones importantes de RAM/VRAM.
- PGF debe seguir funcionando exactamente como antes.

---

# FONTFIX-2 — Normalización visual y baseline

## Objetivo

Hacer que fuentes distintas tengan un tamaño visual similar cuando el usuario selecciona el mismo porcentaje.

## Problema

Actualmente:

```text
20 px FreeType != mismo tamaño visual en todas las fuentes
```

## Propuesta

Calcular o almacenar un factor de normalización por fuente.

Conceptualmente:

```text
final_size = logical_size
           * user_scale
           * font_normalization
```

Ejemplo ilustrativo:

```text
MinSans       1.00
Coolvetica    0.94
Arial Narrow  1.07
UserFont.ttf  auto
```

Los valores reales deben calcularse durante la implementación; los anteriores son solo ejemplos.

## Posibles métricas de referencia

Usar una cadena controlada y medir:

```text
H
x
Ag
0123456789
ABCDEFGHIJKLMNOPQRSTUVWXYZ
```

para estimar:

- altura visual;
- ascender;
- descender;
- baseline;
- anchura media.

## Baseline

Sustituir el desplazamiento fijo actual:

```text
+1 / +2 px
```

por una corrección basada en métricas reales de la fuente cuando sea posible.

## Ajuste del usuario

El control actual de:

```text
50% -> 150%
```

debe mantenerse.

La diferencia es que después de esta fase el usuario lo utilizaría como preferencia personal de accesibilidad/tamaño y no como compensación obligatoria para una fuente con métricas extrañas.

## Criterio de validación

Cambiar entre las fuentes incluidas en el VPK debería mantener aproximadamente la misma jerarquía visual y evitar que botones, tarjetas o encabezados cambien radicalmente de tamaño.

---

# FONTFIX-3 — Cobertura de caracteres y fallback

## Objetivo

Evitar que una fuente personalizada rompa textos de idiomas que no soporta.

## Propuesta

Al cargar/seleccionar una fuente, determinar qué conjuntos de caracteres puede representar.

Como mínimo interesa conocer soporte de:

```text
Latin Basic
Latin Extended
Greek
Cyrillic
CJK / idiomas asiáticos usados por PSVitaAlive
```

## Cadena de fallback propuesta

Conceptualmente:

```text
Fuente seleccionada por el usuario
          |
          v
Fuente Unicode incluida en PSVitaAlive
          |
          v
PGF del sistema
```

Si un carácter no existe en la fuente principal, se dibuja mediante la siguiente fuente disponible.

## Importante

El fallback debe hacerse por glyph/caracter, no sustituyendo necesariamente toda la línea.

Ejemplo:

```text
CustomFont -> "PSVitaAlive "
Fallback   -> "Привет"
```

## Fuente de respaldo

Actualmente `MinSans-Regular.ttf` es considerablemente más grande que otras fuentes incluidas en el proyecto y parece diseñada para una cobertura Unicode mucho más amplia.

Antes de adoptarla formalmente como fallback debe comprobarse su cobertura real y licencia aplicable.

## Criterio de validación

Una fuente personalizada que solo soporte Latin no debe provocar cuadrados, glyphs faltantes o texto ilegible al cambiar el cliente a otro idioma soportado.

---

# 8. Alternativa considerada: modificar libvita2d

Una solución técnicamente posible sería modificar el atlas para usar una clave similar a:

```text
(glyph_index, pixel_size)
```

en vez de:

```text
glyph_index
```

Esto permitiría almacenar varias rasterizaciones de una misma letra dentro de una sola instancia.

## Por qué no se recomienda como primera solución

El atlas seguiría siendo 512x512.

Con múltiples tamaños podría llenarse rápidamente:

```text
A@14
A@16
A@18
A@20
A@22
A@24
...
```

Además obligaría a PSVitaAlive a:

- mantener un parche/fork de `libvita2d`;
- compilar y distribuir una versión propia;
- verificar compatibilidad con futuras actualizaciones de VitaSDK.

Por ello se recomienda primero solucionar el problema dentro de `UiFont`.

---

# 9. Alternativa considerada: convertir todo a PGF

También sería posible abandonar TTF/OTF y exigir fuentes PGF previamente convertidas.

No se recomienda porque:

- reduce la facilidad de personalización;
- obliga al usuario/desarrollador a convertir fuentes;
- limita el ecosistema de fuentes disponibles;
- no resuelve de forma elegante la cobertura Unicode;
- el soporte FreeType actual puede conservarse si se corrige correctamente.

PGF debe mantenerse como opción totalmente compatible, no como única opción.

---

# 10. Orden de implementación recomendado

Cuando se decida trabajar en esta mejora:

```text
FONTFIX-0
   |
   v
validar problema
   |
   v
FONTFIX-1
   |
   v
probar Vita3K + Vita real
   |
   v
FONTFIX-2
   |
   v
validar tamaños/baseline
   |
   v
FONTFIX-3
```

No avanzar a la siguiente fase hasta validar la anterior.

La mejora más importante es:

```text
FONTFIX-1 — FreeType separado por tamaño
```

porque ataca directamente la anomalía encontrada en el atlas de glyphs de `libvita2d`.

---

# 11. Pruebas mínimas futuras

Cada fase debe probarse al menos con:

## Dispositivos

```text
Vita3K
PS Vita real
```

## Fuentes incluidas actualmente

```text
Default PGF
MinSans-Regular.ttf
Coolvetica Rg.otf
arial_narrow_7.ttf
```

más al menos una fuente externa copiada a:

```text
ux0:data/psvitaalive/fonts/
```

## Tamaños

```text
50%
75%
100%
125%
150%
```

## Pantallas

- catálogo;
- tarjetas/listas;
- detalle de aplicación;
- ajustes;
- buscador;
- diálogos;
- noticias/markdown;
- instalación/progreso;
- textos largos y multilínea.

## Idiomas

Probar al menos:

- inglés;
- español;
- un idioma con caracteres Latin Extended;
- cirílico si está disponible;
- cualquier idioma CJK actualmente soportado por el cliente.

---

# 12. Reglas de compatibilidad

La futura implementación debe respetar:

1. `UiFont` continúa siendo la capa de abstracción principal.
2. Los puntos de la UI no deben volver a depender directamente de `vita2d_pgf_*` o `vita2d_font_*` salvo excepciones justificadas.
3. PGF debe seguir funcionando sin cambios visuales inesperados.
4. Las fuentes del usuario en `ux0:data/psvitaalive/fonts/` continúan teniendo soporte.
5. Las fuentes incluidas en `app0:font/` continúan funcionando.
6. El ajuste de tamaño 50%–150% se conserva.
7. No se debe aumentar de forma descontrolada el uso de RAM/VRAM.
8. No se debe mantener un fork de `libvita2d` salvo que las soluciones dentro de `UiFont` resulten insuficientes.
9. Cualquier cambio debe validarse primero en Vita3K y después en hardware real.

---

# 13. Archivos que probablemente estarán implicados

La implementación futura debería concentrarse principalmente en:

```text
Client PSVitaAlive/include/ui/ui_font.hpp
Client PSVitaAlive/source/ui/ui_font.cpp
```

Posiblemente también:

```text
Client PSVitaAlive/include/installer/app_settings.hpp
Client PSVitaAlive/source/installer/app_settings.cpp
Client PSVitaAlive/source/ui/full_catalog_screen.cpp
```

si se añaden nuevos ajustes, información de diagnóstico o controles de fallback.

El objetivo debe ser evitar modificaciones masivas en todos los lugares que dibujan texto.

---

# 14. Resumen

El selector de fuentes actual es una buena base y no necesita ser reemplazado.

El problema más importante identificado es que la ruta FreeType de `libvita2d` reutiliza glyphs de un atlas compartido sin diferenciar correctamente el tamaño con el que fueron rasterizados inicialmente.

PSVitaAlive usa una misma instancia FreeType a múltiples tamaños, por lo que este comportamiento puede producir exactamente las inconsistencias visuales observadas.

La solución recomendada es:

```text
FONTFIX-0 -> medir y reproducir
FONTFIX-1 -> separar/cachar FreeType por tamaño
FONTFIX-2 -> normalizar métricas y baseline
FONTFIX-3 -> cobertura Unicode y fallback
```

Por ahora este documento es únicamente una planificación técnica.

**No hay cambios funcionales implementados asociados a FONTFIX.**
