# Modo de protección de pantalla (OLED/LCD)

## Objetivo

Reducir el tiempo que la interfaz de progreso permanece estática durante descargas, extracciones e instalaciones largas, especialmente en PS Vita 1000 con panel OLED, sin cambiar la política actual de mantener la consola y la pantalla encendidas mientras existe un trabajo activo.

Este sistema es **solo de presentación e input**. No modifica libcurl, el instalador, el extractor, las colas de instalación, los bloqueos del botón PS ni los `sceKernelPowerTick` existentes.

## Comportamiento

- La ventana normal de progreso no se mueve.
- El temporizador se inicia al entrar en una fase activa reconocida como `Downloading`, extracción o instalación.
- Tras **60 segundos** en la misma fase aparece el modo de protección.
- Al cambiar de fase (por ejemplo, Descargando → Extrayendo → Instalando) se restaura inmediatamente la interfaz normal y empieza un nuevo temporizador de 60 segundos.
- Al finalizar, fallar o cancelar el trabajo, el modo de protección se desactiva inmediatamente y no puede volver a activarse hasta que exista otra fase activa compatible.
- Si el usuario sale manualmente del protector y la misma fase continúa, se concede un nuevo periodo normal de 60 segundos antes de poder entrar de nuevo.

## Presentación

- Resolución objetivo de PS Vita: **960 × 544**.
- Fondo del protector: **negro puro** (`#000000`) siempre, independientemente del tema.
- Bloque lógico de contenido: **430 × 150 px**. No se dibuja panel ni borde alrededor del bloque.
- El bloque mantiene un margen de seguridad de 16 px respecto a los bordes de la pantalla.
- El bloque muestra únicamente:
  - `PSVitaAlive`;
  - fase actual localizada: Descargando / Extrayendo / Instalando;
  - porcentaje;
  - ETA;
  - mensaje localizado para volver a la interfaz normal.
- Los colores del texto usan la paleta activa (`ACCENT`, `TEXT`, `DIM`).
- El render usa `UiFont`, por lo que respeta la fuente/estilo y la escala seleccionados por el usuario.

## Movimiento anti-retención

Cada **120 segundos** mientras el modo de protección sigue activo, el bloque se reposiciona de forma pseudoaleatoria dentro del área segura. La selección intenta evitar posiciones demasiado próximas a la anterior (140 px en X o 80 px en Y como distancia mínima útil), manteniendo siempre los 430 × 150 px completamente visibles.

## Input

Cualquier pulsación nueva de un botón que llegue al cliente cierra el modo de protección y **consume esa pulsación**. Esto es importante para que Círculo no cancele accidentalmente una descarga al usarse para despertar la interfaz.

El panel táctil frontal también puede despertar la interfaz. El toque se consume hasta que el dedo se levanta para impedir que llegue a los controles inferiores.

## Multidioma

Los nombres de fase reutilizan los `TextId` existentes (`StageDownloading`, `StageExtracting`, `StageInstalling`). El mensaje del protector utiliza la clave:

```text
PROTECTION_PRESS_ANY_BUTTON
```

La clave se incluye en los paquetes `en`, `es`, `fr`, `de`, `it`, `pt-BR`, `pt-PT` y `ru`.

## Implementación

La lógica vive en `Client PSVitaAlive/source/ui/full_catalog_screen.cpp` para reutilizar el estado de progreso, tema, fuente, localización e input ya existentes sin introducir un segundo sistema de descarga o instalación.

Los estados principales son:

```text
Fase activa
   ↓
60 s en la misma fase
   ↓
Modo protección
   ├─ botón/toque → UI normal + nuevo margen de 60 s
   ├─ 120 s → nueva posición segura
   ├─ cambio de fase → UI normal + nuevo temporizador
   └─ fin/error/cancelación → UI/resultados normal, protector desactivado
```

## Pruebas recomendadas en Vita real

1. Descargar un archivo durante menos de 60 s: el protector no debe aparecer.
2. Mantener una descarga más de 60 s: debe aparecer con fondo negro, porcentaje y ETA.
3. Mantener el protector más de 120 s: el bloque debe cambiar de posición sin recortarse.
4. Pulsar Círculo mientras el protector está activo: debe volver a la UI y **no** cancelar con esa primera pulsación.
5. Repetir con X, Triángulo, D-Pad y touch.
6. Verificar una extracción larga y una instalación larga.
7. Verificar una secuencia Install All: cada cambio de fase debe volver a la UI normal y reiniciar el minuto.
8. Completar, cancelar y forzar un error: el protector no debe reaparecer después del resultado.
9. Probar varios temas: el fondo debe seguir negro y solo deben cambiar los colores de texto.
10. Probar varias fuentes, escalas e idiomas, comprobando que las líneas siguen dentro del bloque de 430 × 150.
11. Confirmar que la consola continúa con las protecciones actuales de suspensión/apagado durante todo el trabajo.

## Nota

El modo reduce contenido estático y áreas iluminadas, pero no pretende garantizar la eliminación absoluta de retención o desgaste del panel. Su objetivo es minimizar de forma práctica el riesgo durante operaciones largas sin alterar el funcionamiento del instalador.
