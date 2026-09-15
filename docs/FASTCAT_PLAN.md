# PSVitaAlive FastCatalog

> **Estado:** propuesta documentada, **no implementada**.
>
> Este documento describe una posible optimización futura para reducir drásticamente el tiempo de carga de los catálogos en el cliente de PS Vita y en la web sin cambiar la fuente de verdad del proyecto ni depender de servidores propios.

## 1. Objetivo

Reducir el tiempo necesario para abrir y cambiar entre catálogos en PSVitaAlive, especialmente en PS Vita real, manteniendo:

- búsqueda;
- filtros;
- orden;
- favoritos;
- categorías y subcategorías;
- perfiles de autor;
- detección de aplicaciones instaladas;
- detección de actualizaciones;
- fechas de versión;
- iconos, portadas y screenshots;
- múltiples fuentes de descarga;
- instalación de VPK/PKG y archivos complementarios;
- compatibilidad con los catálogos actuales;
- funcionamiento sin servidores propios.

La prioridad es disminuir el costo de descarga, parseo, asignaciones y construcción de estructuras en memoria sin romper la experiencia actual.

---

## 2. Arquitectura oficial que NO debe cambiar

La fuente de verdad continúa siendo:

```text
apps/ + authors/ + categories/
        |
        v
   GitHub Actions
        |
        v
catalog.json + authors.json + categories.json
        |
        +--> Cliente PS Vita
        +--> Sitio web
```

Los archivos generados nunca se editan manualmente.

FastCatalog añadiría **artefactos derivados**, pero no reemplazaría esta arquitectura ni convertiría esos artefactos en fuentes editables.

Las fuentes externas, incluyendo VitaDBtoo u otras, continúan siendo únicamente entradas de descubrimiento/importación/enriquecimiento.

---

## 3. Problema actual

El cliente ya posee un sistema de caché local y comprobación de cambios mediante validadores HTTP. Esa parte es útil y debe conservarse.

El cuello de botella principal aparece al cargar un catálogo grande:

```text
archivo JSON
   |
   v
sce::Json::Parser
   |
   v
árbol JSON completo en memoria
   |
   v
recorrido de cada aplicación
   |
   v
CatalogItem
```

Durante el parseo pueden convivir temporalmente:

1. el archivo descargado;
2. el árbol interno de `sce::Json`;
3. las cadenas y arrays del DOM JSON;
4. los `CatalogItem` finales.

Esto provoca muchas asignaciones y bastante trabajo de CPU en una PS Vita.

### Tamaños observados al redactar esta propuesta

Aproximadamente:

- Homebrew `catalog.json`: ~2.06 MB.
- PS Vita `catalog_psvita_games.json`: ~8.23 MB.
- PSP `catalog_psp_games.json`: ~1.71 MB.
- PS1 `catalog_ps1_games.json`: ~0.95 MB.
- `authors.json`: ~0.30 MB.

El catálogo de PS Vita es actualmente el peor caso.

El tamaño en disco no representa el uso real durante el parseo: un JSON de varios MB puede requerir bastante más memoria y CPU cuando se convierte en un DOM completo.

---

## 4. Referencias estudiadas

### PKGj

PKGj utiliza bases tabulares simples (TSV) y evita construir un árbol JSON grande. Este enfoque es especialmente adecuado para una consola con recursos limitados.

La lección útil para PSVitaAlive no es copiar su arquitectura completa, sino adoptar la idea de un **índice plano y barato de parsear** para la navegación.

### VitaDB Downloader

VitaDB Downloader utiliza caché local y evita descargar repetidamente el catálogo cuando no ha cambiado. También carga recursos visuales según se necesitan.

PSVitaAlive ya implementa parte de esta idea mediante caché y validadores HTTP. FastCatalog debe aprovechar y extender ese trabajo, no eliminarlo.

### VitaForge

VitaForge separa la comprobación de versión del catálogo del snapshot completo. Si la versión local coincide, utiliza la caché; si cambia, obtiene una copia nueva.

VitaForge utiliza un servicio propio, pero PSVitaAlive puede aplicar la misma idea mediante un pequeño archivo estático alojado en GitHub/GitHub Pages.

---

## 5. Arquitectura propuesta: FastCatalog

La propuesta separa la información necesaria para **navegar** de la información necesaria para **abrir una ficha completa**.

```text
FUENTES DE VERDAD
apps/ + authors/ + categories/
catálogos comerciales mantenidos por el proyecto
        |
        v
   GitHub Actions
        |
        +--> catálogos JSON completos actuales
        |    (compatibilidad / contrato público)
        |
        +--> catalog_manifest.json
        |
        +--> índices rápidos para PS Vita (.tsv)
        |
        +--> índices rápidos para Web (.json minificado)
        |
        +--> detalles individuales generados (.json)
```

Todos estos nuevos archivos deben ser **generados automáticamente**.

---

## 6. `catalog_manifest.json`

Se propone generar un pequeño manifest estático con la revisión actual de cada catálogo.

Ejemplo conceptual:

```json
{
  "schema": 1,
  "revision": "2026-09-14-abc123",
  "catalogs": {
    "homebrew": {
      "version": "e80a...",
      "items": 1234,
      "index_vita": "generated/homebrew/index.tsv",
      "index_web": "generated/homebrew/index.json",
      "details_base": "generated/homebrew/details/"
    },
    "psvita": {
      "version": "98da...",
      "items": 4237,
      "index_vita": "generated/psvita/index.tsv",
      "index_web": "generated/psvita/index.json",
      "details_base": "generated/psvita/details/"
    }
  }
}
```

También debería incluir, cuando sea útil:

- tamaño de archivo;
- SHA-256;
- versión del esquema;
- número de entradas;
- fecha/revisión de generación.

### Flujo del cliente

```text
abrir PSVitaAlive
      |
      v
descargar/comprobar manifest pequeño
      |
      +--> versión igual --> usar caché inmediatamente
      |
      +--> versión nueva --> descargar nuevo índice
      |
      +--> sin red -------> usar caché existente
```

El manifest no reemplaza el sistema de fallback local.

---

## 7. Índice rápido para PS Vita

### Formato recomendado inicial: TSV

Propuesta:

```text
generated/homebrew/index.tsv
generated/psvita/index.tsv
generated/psp/index.tsv
generated/ps1/index.tsv
```

El índice debe contener solamente los datos necesarios para:

- mostrar tarjetas/listados;
- buscar;
- filtrar;
- ordenar;
- favoritos;
- Title ID;
- categorías/subcategorías;
- autor básico;
- detectar instalación;
- detectar actualización;
- fecha de versión;
- icono o portada;
- tamaño básico;
- estado.

Campos conceptuales:

```text
id	title_id	name	description	author_ids	category_id	subcategory_ids	version	version_date	size	status	icon
```

El formato exacto debe definir de forma explícita:

- UTF-8;
- escaping de tabuladores;
- escaping de saltos de línea;
- representación de listas;
- campos opcionales;
- versión del esquema.

### No incluir inicialmente

El índice rápido no debería incluir datos pesados que solamente se utilizan al abrir la ficha:

- `long_description`;
- changelog completo;
- requirements largos;
- todos los enlaces;
- mirrors;
- DLC;
- screenshots completos;
- zRIF/licencias;
- metadata detallada de instalación;
- `extract_path`;
- información de plugins;
- documentación secundaria.

---

## 8. Parser Vita propuesto

El objetivo es sustituir para el listado el flujo:

```text
JSON -> sce::Json DOM -> CatalogItem
```

por:

```text
TSV -> lectura lineal -> CatalogItemSummary
```

Un parser lineal puede:

1. abrir el archivo;
2. leer bloques o líneas;
3. separar columnas;
4. rellenar la estructura final;
5. descartar inmediatamente el buffer temporal.

El manifest proporciona `items`, por lo que el vector puede reservar capacidad antes de parsear:

```cpp
items.reserve(manifest.itemCount);
```

Esto reduce reallocations.

### Estructura separada

Se recomienda introducir conceptualmente una estructura ligera:

```cpp
CatalogItemSummary
```

para los listados y conservar una estructura de detalle independiente para información completa.

El nombre definitivo puede cambiar durante la implementación.

---

## 9. Detalles bajo demanda

GitHub Actions generaría archivos individuales de detalle:

```text
generated/homebrew/details/<id>.json
generated/psvita/details/<id>.json
generated/psp/details/<id>.json
generated/ps1/details/<id>.json
```

Estos pueden conservar toda la información requerida por la ficha:

- links;
- múltiples descargas;
- mirrors;
- DLC;
- screenshots;
- requirements;
- changelog;
- long_description;
- content_id;
- metadata de instalación;
- extract_path;
- plugins;
- archivos de datos;
- hashes;
- URLs adicionales.

### Flujo

```text
usuario abre ficha
        |
        v
¿detalle válido en caché?
   |               |
  sí              no
   |               |
leer local     descargar JSON pequeño
   |               |
   +-------+-------+
           |
           v
       mostrar ficha
```

Los detalles deben cachearse localmente.

Una actualización de catálogo no debería obligar a borrar toda la caché de detalles si se puede determinar qué aplicaciones cambiaron.

---

## 10. Imágenes

FastCatalog **no debe reemplazar el sistema actual de ImageCache**.

El índice rápido conserva solamente la URL necesaria para tarjeta/listado:

- `icon`, o
- `cover`.

Los screenshots continúan cargándose al entrar en detalle.

Objetivo:

- no descargar screenshots durante la carga del catálogo;
- no mantener texturas innecesarias en RAM;
- conservar la caché visual existente;
- evitar regresiones de scroll.

---

## 11. Web

La web no necesita TSV.

GitHub Actions debería generar versiones JSON minificadas del mismo índice lógico:

```text
generated/homebrew/index.json
generated/psvita/index.json
generated/psp/index.json
generated/ps1/index.json
```

La página principal o cada selector de catálogo cargaría únicamente el índice correspondiente.

La ficha cargaría:

```text
generated/<catalog>/details/<id>.json
```

### Optimización de búsquedas en JavaScript

Al cargar un índice se deberían construir mapas una sola vez:

```js
appById = new Map();
titleIdToApp = new Map();
authorById = new Map();
categoryById = new Map();
```

Esto evita repetir `.find()` sobre arrays grandes.

Cuando sea posible, la web debería consumir recursos relativos de GitHub Pages en lugar de descargar todos los catálogos desde `raw.githubusercontent.com`.

La compatibilidad con el sistema actual debe mantenerse durante la migración.

---

## 12. Caché de catálogos en RAM

Una vez reducido el tamaño de cada índice, se puede evaluar mantener más de un catálogo preparado en memoria.

Propuesta: caché LRU con presupuesto de RAM.

Ejemplo:

```text
RAM:
- PS Vita
- Homebrew

abrir PSP
=> expulsar el catálogo menos usado si se supera el presupuesto
```

No se recomienda fijar simplemente "dos catálogos siempre". El límite debería depender de un presupuesto de memoria medible.

Esto permitiría que cambios repetidos entre catálogos recientes fueran prácticamente instantáneos.

---

## 13. Por qué NO usar SQLite inicialmente

SQLite sigue siendo una alternativa futura válida, pero no se recomienda como primer paso para este problema porque:

- requiere una integración bastante más profunda;
- cambia el modelo de acceso de la UI;
- obliga a mantener una solución distinta para la web;
- añade complejidad de actualización/migración;
- FastCatalog puede eliminar el principal cuello de botella con mucho menos riesgo.

SQLite debería reconsiderarse únicamente si el catálogo crece hasta un punto donde mantener índices completos en RAM deje de ser razonable incluso después de FastCatalog.

---

## 14. Por qué NO crear un formato binario inicialmente

Un formato binario personalizado podría ser todavía más rápido, pero añade:

- versionado binario;
- mayor dificultad de depuración;
- herramientas adicionales;
- más riesgo de incompatibilidad;
- mayor costo de mantenimiento.

El orden recomendado es:

```text
TSV primero
   |
   v
medir en Vita real
   |
   +--> suficientemente rápido --> mantener TSV
   |
   +--> insuficiente -----------> evaluar binario
```

El formato binario queda reservado como una segunda generación posible.

---

## 15. Compatibilidad

La migración debe ser gradual.

Durante la transición se deben seguir generando los catálogos JSON completos actuales.

El cliente debe poder utilizar temporalmente:

```text
FastCatalog disponible
        |
       sí
        v
usar índice rápido

FastCatalog no disponible / corrupto
        |
        v
fallback al catálogo JSON actual
```

No retirar el parser antiguo hasta completar pruebas reales.

---

## 16. Fases oficiales propuestas

### FASTCAT-0 — Medición

**Objetivo:** obtener una línea base real antes de modificar formatos.

Añadir métricas al logger para medir por catálogo:

- tiempo de comprobación de red;
- tiempo de descarga;
- bytes descargados;
- tiempo de lectura desde disco;
- tiempo de parseo JSON;
- tiempo de construcción de items;
- tiempo hasta `publishReady`;
- número de entradas;
- RAM antes/después cuando sea medible;
- diferencia entre Vita real y Vita3K.

**No cambia el comportamiento funcional.**

**Criterio para avanzar:** disponer de mediciones reproducibles de los cuatro catálogos.

---

### FASTCAT-1 — Manifest y caché versionada

**Objetivo:** evitar validaciones y descargas innecesarias de archivos grandes.

Implementar:

- `catalog_manifest.json`;
- versión/hash por catálogo;
- conteo de items;
- tamaño;
- SHA-256;
- caché local del manifest;
- fallback offline;
- minificación de artefactos generados donde sea apropiado.

**Criterio para avanzar:** abrir una caché vigente sin descargar el catálogo completo y sin regresiones offline.

---

### FASTCAT-2 — Vita Fast Index

**Objetivo:** eliminar el DOM JSON grande del camino crítico del listado.

Implementar:

- generación de `index.tsv`;
- esquema versionado;
- parser lineal;
- `CatalogItemSummary` o equivalente;
- búsqueda;
- filtros;
- orden;
- favoritos;
- categorías;
- detección de instalados;
- detección de actualizaciones;
- fecha de versión;
- iconos/portadas.

Mantener fallback JSON.

**Criterio para avanzar:** todas las funciones del listado deben comportarse igual que con el catálogo actual y el tiempo de carga debe mejorar claramente en Vita real.

---

### FASTCAT-3 — Lazy Details

**Objetivo:** sacar del índice todo lo que solamente necesita la ficha.

Implementar:

- generación de `details/<id>.json`;
- descarga bajo demanda;
- caché local;
- invalidación por versión/hash;
- fallback al catálogo antiguo;
- links;
- screenshots;
- requirements;
- changelog;
- múltiples descargas;
- DLC;
- metadata de instalación.

**Criterio para avanzar:** todas las fichas e instalaciones deben conservar las capacidades existentes.

---

### FASTCAT-4 — Web Fast Index

**Objetivo:** aplicar la separación índice/detalle al sitio web.

Implementar:

- `index.json` minificado por catálogo;
- detalle individual;
- `Map` por ID/Title ID/autor/categoría;
- recursos relativos de GitHub Pages cuando sea viable;
- fallback durante transición.

**Criterio para avanzar:** búsqueda, filtros, autores, categorías y fichas deben funcionar igual o mejor que antes.

---

### FASTCAT-5 — RAM/LRU

**Objetivo:** hacer casi instantáneo el regreso a catálogos utilizados recientemente.

Implementar una caché LRU de índices bajo un presupuesto explícito de RAM.

**Criterio para avanzar:** no producir OOM, degradación de ImageCache ni regresiones de scroll.

---

### FASTCAT-6 — Retirar compatibilidad antigua del cliente

**Objetivo:** simplificar solamente cuando FastCatalog esté plenamente validado.

Antes de eliminar código antiguo debe probarse:

- Vita real;
- Vita3K;
- red rápida;
- red lenta;
- offline;
- caché corrupta;
- actualización de catálogo;
- cambio repetido de catálogos;
- búsqueda;
- filtros;
- favoritos;
- instalación;
- actualización de apps;
- screenshots;
- autores;
- DLC/links especiales.

Los JSON completos pueden continuar generándose como contrato público incluso si el cliente deja de utilizarlos directamente.

---

### FASTCAT-BINARY — Opcional

No forma parte de la primera implementación.

Solo evaluar si, después de `FASTCAT-2`, las mediciones en Vita real demuestran que TSV sigue siendo insuficiente.

Posible formato futuro:

```text
catalog.vcat
```

Debería tener:

- magic/version;
- offsets;
- longitudes explícitas;
- validación de bounds;
- endian definido;
- checksum/hash;
- parser tolerante a corrupción;
- herramienta de inspección para PC.

---

## 17. Reglas de implementación

1. No cambiar la fuente de verdad del catálogo.
2. No editar manualmente archivos generados.
3. No depender de servidores propios.
4. Mantener GitHub Actions + GitHub Pages.
5. Mantener compatibilidad temporal con los JSON existentes.
6. Medir antes y después de cada fase.
7. No avanzar a una nueva fase sin validar la anterior.
8. Probar en Vita real además de Vita3K.
9. No degradar ImageCache ni scroll.
10. No aumentar innecesariamente el uso de RAM.
11. Evitar duplicar lógica entre web y cliente cuando el generador pueda resolverla.
12. Toda estructura generada debe tener una versión de esquema.
13. Los detalles deben poder invalidarse individualmente en el futuro.
14. Mantener fallback offline.

---

## 18. Métricas de éxito

Las metas concretas se fijarán después de `FASTCAT-0`, pero se deben medir como mínimo:

```text
T_open_cached
T_open_first_download
T_parse
T_publish_ready
RAM_peak
RAM_after_load
bytes_downloaded
```

por cada catálogo.

La optimización se considerará satisfactoria cuando:

- el catálogo cacheado aparezca en pocos segundos en Vita real;
- el cambio entre índices pequeños sea claramente más rápido que el sistema JSON actual;
- no haya OOM;
- no se pierdan funciones actuales;
- la web descargue menos datos para navegación normal;
- el sistema offline continúe funcionando.

No se debe definir una mejora únicamente por tamaño de archivo: la métrica principal es **tiempo real hasta que el usuario puede navegar el catálogo**.

---

## 19. Orden recomendado cuando se retome

```text
FASTCAT-0
   |
validar mediciones
   |
FASTCAT-1
   |
validar caché/versiones
   |
FASTCAT-2
   |
medir en Vita real
   |
FASTCAT-3
   |
validar fichas/instalación
   |
FASTCAT-4
   |
validar web
   |
FASTCAT-5
   |
pruebas de memoria
   |
FASTCAT-6
```

`FASTCAT-BINARY` solo debe estudiarse si las métricas posteriores a `FASTCAT-2` justifican esa complejidad.

---

## 20. Resumen de decisión

La dirección recomendada para una implementación futura es:

> **manifest pequeño + caché versionada + índice plano ligero para Vita + JSON compacto para web + detalles bajo demanda.**

Esta solución intenta combinar las ventajas observadas en proyectos como PKGj, VitaDB Downloader y VitaForge, pero manteniendo los principios propios de PSVitaAlive:

- gratuito;
- sin backend propio;
- escalable;
- compatible con GitHub Pages;
- modular;
- amigable con hardware real de PS Vita;
- compatible con Homebrew moderno y antiguo.

Por ahora este documento es únicamente una especificación de trabajo futuro. Ningún cambio funcional debe considerarse aprobado o implementado hasta iniciar explícitamente `FASTCAT-0`.
