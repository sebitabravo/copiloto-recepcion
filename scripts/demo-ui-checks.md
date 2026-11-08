# Verificación de la demo: recepción y traza

## Ejecutar desde la raíz del repositorio

Sin dependencias nuevas, servicios ni acceso de red:

```sh
node --test scripts/test-demo-ui.mjs
node --check landing/console.js
git diff --check -- landing/console.js scripts/test-demo-ui.mjs scripts/demo-ui-checks.md
```

La suite Node ejecuta los scripts reales en un DOM mínimo con `fetch`, almacenamiento y temporizadores simulados. No hace HTTP real, no crea reservas ni modifica conversaciones. El POST existente de sesión demo también es simulado; cola y detalle solo usan GET con cookies y sin caché. Los registros de cola existen únicamente en las pruebas, nunca como respaldo del producto.

## Comportamiento cubierto

- `#queue-search`: búsqueda local sin distinguir mayúsculas y con espacios exteriores ignorados; busca nombre presentado al usuario (incluido «Visitante web»), ID, paso original y etiqueta del paso.
- `#queue-filter`: Todas, Necesita una persona, Por vencer y Vencidas. Se combina con la búsqueda; usa `waitRisk` y los umbrales recibidos del servidor, incluidos sus límites exactos. No reordena ni altera los registros.
- `#queue-result-count`: «Mostrando X de Y conversaciones», anunciado como estado. El resumen conserva el total y los riesgos de toda la cola recibida, no solo del subconjunto visible. Los contadores tienen texto, no dependen del color.
- «Actualizar cola» vuelve a consultar GET `/api/panel/queue`; conserva búsqueda y prioridad. Los controles explicitan esa fuente y el orden del servidor. No se añade polling: se conserva el intervalo existente de diez segundos, detenido al salir de Recepción y sin consultar la cola mientras hay un detalle seleccionado.
- Sin coincidencias: «No hay coincidencias con esta búsqueda y filtro. Cambia los criterios para ver más conversaciones.» No equivale a «Sin conversaciones todavía. Cuando un huésped escriba, aparece acá.». Ambos estados permiten actualizar la cola; una cola vacía muestra 0 de 0.
- Detalle, vuelta a la cola y refresco conservan los criterios. Los controles se ocultan durante carga, detalle y barreras de sesión; vuelven tras una lectura correcta. Se preservan reintentos, modo manual, sesión demo, estados 401/403/429/error y carga diferida del PMS.
- Inputs/selects tienen etiquetas asociadas y ayuda; nombres, pasos y notas se representan como texto, sin interpretar HTML.
- La traza permanece cerrada después de una respuesta/propuesta. Las pruebas abren el control, comprueban contenido y ARIA y lo cierran. La propuesta visible en chat sigue exigiendo confirmación explícita de un solo uso. La consulta guiada de disponibilidad mantiene sus tres turnos seguros en todos los modos.

## Alcance y seam con presentación

`console.js` crea los controles dentro de `#reception-tools` si existe. Sin ese contenedor, los inserta antes de la cola en su padre; si la cola está separada, usa `#recepcion-console`. Las pruebas cubren las tres estructuras. Presentación utiliza `.queue-toolbar`, `.queue-tool-field` y `.queue-filter-empty`; debe respetar `[hidden]`.

Esta evidencia **no es una prueba de navegador ni de integración backend**. El DOM mínimo no mide layout, foco nativo, lectores de pantalla, caché del navegador ni comportamiento visual responsive. Tampoco comprueba IA, voz, Chatwoot, PMS o autenticación real. La cola de recepción no recibe datos inventados del simulador ni implica una derivación real desde él.

La verificación posterior del padre debe revisar controles y mensajes en navegador con respuestas interceptadas y explícitamente identificadas como simuladas, integración HTML/CSS y actualización de la versión de `console.js` en el HTML para evitar recursos inmutables cacheados. No ejecutar flujos de escritura contra servicios reales para obtener esa evidencia.

## Evidencia de esta unidad

- Baseline heredado: 25 pruebas, 23 pasan; dos expectativas antiguas exigían traza autoabierta.
- RED observado tras actualizar esas expectativas y añadir recepción: 31 pruebas, 25 pasan, 6 fallan por controles ausentes; exit 1.
- Primer intento GREEN: timeout de 120 s en el test de refresco diferido porque esperaba su propia promesa pendiente. Se corrigió la secuencia de la prueba, no el producto.
- GREEN observado: 31 pruebas, 31 pasan, 0 fallan; exit 0. Las comprobaciones de sintaxis y whitespace se reportan por separado en el handoff.
