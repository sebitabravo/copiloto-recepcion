# /demo: probar el producto sin cambiar de ruta

La demo es un espacio de trabajo con tres perspectivas, no una lista de pasos completados. La cabecera compacta deja el protagonismo a la conversación y sus controles. La portada (`index.html`) y sus estilos no cambian.

## Guion breve para la demostración

1. Abre `/demo` y presenta la idea: **un copiloto que responde consultas del hotel y deja al equipo revisar su operación**.
2. Pulsa **«Empezar: ubicación y servicios»**. El guion envía dos consultas al servidor; señala la respuesta dentro del teléfono, no una métrica técnica.
3. Abre **«Ver qué consultó»** para mostrar el origen de la respuesta. Si hay un error, explica el estado observado; no lo presentes como una respuesta correcta.
4. Pasa a **Recepción**, filtra la cola y abre una conversación. Aclara que esta cola es independiente del chat de prueba: no se está mostrando una transferencia de ese historial.
5. Pasa a **Administración** para enseñar el sistema de gestión del hotel (PMS) y amplía la vista si hace falta. No es necesario crear una reserva para explicar su función.

La voz es una alternativa visible en **«Probar por voz»** y en el teléfono. Ensaya audio/micrófono en tu entorno antes de usarlos ante la audiencia; la evidencia automatizada disponible no los certifica.

## Recorrido útil

1. **Huésped:** escribe, usa una consulta guiada o llama con el icono del teléfono. Las consultas guiadas envían mensajes al servidor; no son una reproducción local.
2. **Recepción:** usa «Ver cola de recepción» para leer espera, riesgo de SLA y contexto. La cola viene del servidor de recepción, no del historial de este simulador. Las acciones entre perspectivas activan y enfocan la pestaña real sin cambiar `/demo`.
3. **Administración:** «Explorar PMS» carga el PMS simulado existente. «Ampliar PMS» aumenta su altura en la página; «Reducir PMS» revierte el cambio. No abre otra ruta ni recarga el iframe.

## Qué representa cada superficie

| Superficie | Origen y límites |
| --- | --- |
| Conversación y voz | `demo.js` y `voice.js` conservan sus controles, escenarios, propuestas y errores. El permiso de creación de reservas simuladas depende del servidor; no hay una confirmación ficticia del recorrido. |
| Derivación del simulador | No notifica a recepción ni transfiere el historial a Chatwoot. |
| Canal real | Disclosure «Canal real de recepción». Solo «Abrir el chat de recepción» carga/abre el widget existente, sujeto a configuración y conexión. Los enlaces `#canal`, incluidos los directos, revelan la perspectiva y el disclosure. Abrir el disclosure no envía mensajes. |
| Recepción | Vista de solo lectura. `console.js` conserva sesión, sondeo, filas y detalle. `#reception-tools` es un contenedor opcional para su búsqueda/filtros/refresco; el módulo de recorrido no implementa lógica de cola. |
| PMS | Iframe conectado a datos ficticios persistidos por el servicio. Las acciones dentro del PMS pueden modificar esos datos de prueba; ampliar la vista no los modifica. |
| Diagnóstico | Disclosure nativo `#demo-diagnostics`: traza y consultas existentes de estado/configuración/métricas. Ningún resultado aparece como comprobado antes de consultarlo. |
| Modo demo | Es acceso/sesión para recepción y PMS, no un selector de simulación local desconectada. Su comportamiento y banner siguen a cargo de `console.js`. |

«Ver qué consultó» está siempre fuera del diagnóstico, cerrado inicialmente. `demo.js` sigue controlando la traza y su ARIA; el módulo de recorrido solo abre el ancestro y desplaza la traza a la vista cuando se pide mostrarla. Los disclosures se pueden volver a cerrar con teclado o puntero.

## Composición y mantenimiento

- `demo-console.css` reutiliza colores, fuentes y sombras de `design/system.md`. En móvil los escenarios y el control de traza van **antes** del teléfono; el contexto secundario queda después. No se reduce el texto explicativo por debajo de 12 px para encajar la cabecera.
- Nuevos controles y campos tienen objetivos de al menos 44 px. El compositor y la entrada de voz usan 16 px; las superficies nuevas heredan los tokens oscuros y no añaden animaciones.
- `demo-journey.js` se carga después de `console.js`: no sustituye la selección de pestañas, no controla credenciales y no hace peticiones. La ampliación añade/quita `.is-expanded` y sincroniza `aria-expanded`.
- Las tarjetas de Recepción y Administración conservan 26 px de padding interior (20 px en ≤620 px), también al ampliar el PMS. La regla específica `.tab-panel > .console-card` prevalece sobre el reset de secciones de `demo.css`, sin afectar al teléfono ni a `[hidden]`.
- Versiones de la pasada de comprensión: `demo-console.css`, `demo-journey.js` y `demo.js` usan `20261109c`; `console.js` conserva `20261109a`. `demo.css` y `voice.js` no cambian. La consulta recomendada reutiliza el guion `info`; el atajo de voz delega en el botón existente y no reinicia una llamada activa.

## Verificación segura y límites

`node --test scripts/test-demo-journey.mjs` ejecuta los handlers reales del módulo de recorrido sobre un DOM derivado del HTML, con propietarios de pestañas/traza representados por spies. Cubre navegación y foco, ruta estable, disclosures, enlaces directos, expansión/ARIA y ausencia de invocaciones a controles independientes. No prueba el backend, el SDK de Chatwoot, el reconocimiento de voz ni el renderizado del navegador. La suite de los módulos existentes corresponde a la unidad B y al padre.

Comprobado en navegador por el padre con servicios interceptados (no integración backend):

- [x] A 390×844: cabecera compacta, controles y comienzo del chat dentro del primer viewport, sin overflow horizontal; repetir a 320 px y escritorio.
- [x] Recorrido entre las tres vistas con teclado, foco visible y traza realmente visible al abrirla desde el diagnóstico cerrado.
- [x] `#canal` desde Recepción, enlace directo y navegación del historial; no abrir el SDK automáticamente.
- [x] Ampliar/reducir PMS sin perder acceso al control ni provocar navegación o recarga.
- [x] Búsqueda/filtros/refresco de B dentro de `#reception-tools`, vacío filtrado, detalle y regreso.
- [x] Tema oscuro y movimiento reducido; chat y voz escrita con respuestas interceptadas etiquetadas, sin mensajes ni cambios operativos reales.

La suite conjunta `node --test scripts/test-demo-ui.mjs scripts/test-demo-journey.mjs` pasó 44/44 tras añadir cobertura de primer paso recomendado, voz visible y lenguaje del control de consultas. En navegador se comprobaron las tres perspectivas a 320/390/768/1024/1920 px en claro y oscuro: sin desbordamiento horizontal ni controles visibles menores a 44 px. El iframe de prueba cargó una vez y pasó de 700 a 880 px al ampliar; no se operó el PMS real. Las respuestas interceptadas incluyeron errores 503 deliberados y datos sintéticos; no hubo escrituras operativas. El verificador Python anterior sigue no disponible (exit 127) y no se reintentó.

Esta unidad cubre **S1/S2** (jerarquía y sistema visual), **S3** (reglas deterministas de navegación/disclosure/ampliación), **S5** (perspectivas en la misma ruta) y **S6/S7** (iteración funcional sustantiva coordinada con recepción). No cierra la validación integral ni sustituye evidencia visual o de integraciones.
