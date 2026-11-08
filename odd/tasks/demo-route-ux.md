# Ruta demo — tour claro del producto
Estado: en ejecución · Rama: `refactor/ux-logic-cleanup` · Estrategia: `ask-on-risk` (commits de unidad; sin publicación solicitada)
Pruebas: suite Python/pytest existente en `copiloto/tests/test_demo_*`; intérprete compatible no verificado; runner frontend no identificado.

## Specs

S1. El alcance pedido por el usuario es: “la landing page esta perfecto el tema es la ruta de la demo de como se representa esta desordenado y feo nose siento que no esta bien y no funciona bien no representa todo el potencial”.

S2. El pedido de investigación e implementación es: “ya dale investiga en internet como seria la mejorar manera para mejorar esa gran falencia que tiene mi pagina y mejoras porfavor para lograr presentar el potencial del proyecto porfavor”.

S3. La preocupación funcional expresada por el usuario es: “si es que funciona correectamente todas las cosas”.

S4. Autorización explícita de diseño: “Sí, sincroniza y continúa”.

S5. Restricción de producto ya expresada por el usuario en `odd/tasks/landing-producto.md`, L6: “y asi se tiene en esa vista el acceso a todas las funcionalidades y el usuario no tiene que estar entrando a rutas y cosas raras ya que asi llega a prueba nomas las cosas como si de whassap se tratara y se ve la perspectiva tanto del cleinte como la del genrente del hotel y la del admin”.

## Tasks

| ID | Alcance | Ruta | Specs | Estado | Commit / evidencia |
| --- | --- | --- | --- | --- | --- |
| T1 | Sincronizar `design/system.md` y `design/system.html` con las fuentes visuales actuales | Delegado: `gentle-ai-worker` (context backstop; superficies exactas en el handoff) | S2, S4 | done | `49310ba` — `docs(design): refresh current demo design system` |
| T2 | Crear tres direcciones visuales distintas para `/demo` y elegir la que mejor cuenta el valor del proyecto | Padre con Gentle Design | S1, S2, S5 | done | `3216aff` — `design(demo): add guided demo directions` |
| T3 | Implementar la dirección elegida en la ruta de demo conservando las capacidades existentes | Padre, inline | S1, S2, S3, S5 | done | `landing/demo.html`, `landing/demo-console.css`, `landing/demo.js`, `landing/voice.js`; assets `20261108a`/CSS `20261108b`; `git diff --check` pasó |
| T4 | Verificar interacciones, accesibilidad y adaptación de la demo; registrar cualquier runner no disponible | Padre | S3 | done | Playwright aislado: pestañas/disclosure, snapshot semántico y 320/390/768/1024/1920 sin overflow; 317 px de teléfono visibles en 390×844; aviso de voz servido correcto. Sin mensajes ni reservas |
| T5 | Cerrar unidades revisadas, registrar commits y comunicar resultado y límites | Padre | S1–S4 | in_progress | Revisar superficie/riesgo, estado Gentle Design, diff final y cerrar el commit de implementación; no publicar |

## Log

L1 (usuario, solicitud original verbatim): “mira necesito que me revices el proyecto si es que realmente se ve todo bien y si es que funciona correectamente todas las cosas porfavor porque veo problemas de ux/ui severos hay partes que siento que no tineen sentido entonces necesito una auditoria si ees que la demo esta bien implementada la landing page esta perfecto el tema es la ruta de la demo de como se representa esta desordenado y feo nose siento que no esta bien y no funciona bien no representa todo el potencial. C:\Users\sebitabravo\Pictures\Screenshots\Screenshot 2026-11-07 210327.png C:\Users\sebitabravo\Pictures\Screenshots\Screenshot 2026-11-07 210319.png entonces analisa la pagina con cuidado porfavor.”

L2 (usuario, nueva solicitud verbatim): “ya dale investiga en internet como seria la mejorar manera para mejorar esa gran falencia que tiene mi pagina y mejoras porfavor para lograr presentar el potencial del proyecto porfavor.”

L3 (usuario, autorización): eligió “Sí, sincroniza y continúa” para sincronizar el sistema visual y continuar con el diseño e implementación.

L4 (evidencia de auditoría previa): `Screenshot 2026-11-07 210319.png` muestra una cola con 40 conversaciones, 20 vencidas y esperas aproximadas de 19–22 horas; `Screenshot 2026-11-07 210327.png` muestra el PMS dentro de un iframe con scroll propio. `landing/demo.html` reúne las pestañas Huésped/Recepción/Admin; `landing/demo-console.css` limita el iframe a `min(70vh, 720px)`. El copy de derivación difiere entre `landing/demo.js` y `landing/voice.js`. No se editó la cola ni el backend.

L5 (investigación web, evidencia y recomendación): Storylane, “Best Practices”, https://docs.storylane.io/best-practices (fecha no visible): recomienda “create compelling narratives that address relevant pain points and use cases.” NN/g, “Progressive Disclosure”, https://www.nngroup.com/articles/progressive-disclosure/ (fecha no verificada): “Initially, show users only a few of the most important options”. NN/g, “Audience-Based Navigation: 5 Reasons to Avoid It”, https://www.nngroup.com/articles/audience-based-navigation/ (fecha no verificada): usuarios “must ask themselves who the site thinks they are”. ProductLed, “Activation Velocity”, https://productled.com/blog/activation-velocity (fecha no verificada): define medir el logro de un hito de activación por cohorte y tiempo. Recomendación propia: priorizar una historia huésped → copiloto → resultado/derivación a recepción, dejando el PMS como exploración secundaria; la fuente no prescribe esa estructura específica.

L6 (evidencia de setup): `gentle_design list` indicó que `design/system.md` estaba desactualizado respecto de `landing/demo.css`. El usuario autorizó sincronizar antes de diseñar. El proyecto tiene dos sistemas visuales en `landing/demo.css` y `copiloto/src/copiloto/static/theme.css`; no deben unificarse sin evidencia.

L7 (verificación heredada): la suite `test_demo_api.py`, `test_demo_session.py`, `test_demo_voice.py` y `test_demo_concurrency.py` no se ejecutó en la auditoría anterior: el verificador salió con código 127 porque faltaba su intérprete en la copia aislada. No se debe afirmar que la demo quedó verificada en vivo a partir de esa suite.

L8 (baseline de navegador, contexto aislado): `http://localhost:8080/demo` cargó el título y la página de demo. `http://localhost:8100/demo` respondió 404; ese puerto pertenece al servicio API, mientras `landing` se publica en 8080 según `infra/docker-compose.yml`. No se envió ningún mensaje ni se creó una reserva.

L9 (baseline accesible, contexto aislado): el árbol de accesibilidad de Huésped presenta bajo una sola pestaña el simulador, la traza técnica, el canal Chatwoot y tres tarjetas de estado/métricas; la región principal mide ~1906 px de alto en el viewport observado (~1905 px de ancho). Esto confirma el problema de jerarquía, no un fallo de CSS roto.

L10 (restricción vigente): `odd/tasks/landing-producto.md`, L6 conserva el pedido de que la misma vista permita probar las perspectivas de huésped, recepción y administración. La dirección será historia guiada primero, con las tres perspectivas todavía accesibles en `/demo`; no se separarán en rutas.

L11 (incidente Git, antes de commit): `pwd -W` reportó `C:/Users/sebitabravo/Developer/copiloto-recepcion`, pero `git rev-parse --show-toplevel` y la lista de worktrees identificaron `D:/Projects/copiloto-recepcion` como raíz principal y no incluyeron la ruta C:. No se hizo `git add` ni commit antes de resolver la diferencia.

L12 (resolución y autorización): el usuario eligió “Autoriza la raíz D:”. La comparación de rutas mostró el mismo dispositivo e inode para ambas carpetas y hashes idénticos para `design/system.md`, `design/system.html` y `odd/tasks/demo-route-ux.md`; C: es un alias del mismo árbol que Git identifica en D:. Se continúa allí.

L13 (T1 completada): el trabajador actualizó solo los dos documentos del sistema; el CSS fuente no cambió. `git diff --check` y la comprobación del commit pasaron; árbol limpio tras `49310ba` (`docs(design): refresh current demo design system`). ASSESS sobre el commit dio riesgo medio por el board HTML, `reviewDue: false` (`under_budget`) y sin verificador independiente; no se inició revisión nativa.

L14 (T2 diseño y selección): `design/demo-route-ux/` contiene tres direcciones y su `design.json`: A `01-recorrido-guiado.html`, B `02-consola-por-roles.html`, C `03-caso-punta-a-punta.html`, con tradeoffs en el manifiesto. Seleccionada A por empezar con el valor, revelar detalle progresivamente y conservar Huésped/Recepción/Administración en `/demo`, sin confundir la derivación simulada con el canal real. Las tres se revisaron visualmente en Gentle Design (48%); la auditoría de colores confirmó solo valores del sistema, las familias usan los fallbacks del board y seis combinaciones de texto/superficie pasaron WCAG AA. Preview: `http://127.0.0.1:51399/WJ3iCRsZSHtc9WykToYWHD5w2dnL0NPj/d/demo-route-ux/`. Los 19 errores de consola correspondieron al servicio del canvas (CSP con fuentes IPv6 inválidas y favicon 404 inicial), no a las artboards.

L15 (T2 cerrada): commit `3216aff` (`design(demo): add guided demo directions`); `git show --check` pasó y el árbol quedó limpio. ASSESS sobre el rango comprometido indicó riesgo medio, `reviewDue: false` (`under_budget`) y ningún verificador independiente; no se inició revisión nativa.

L16 (T3 implementada; T4 en curso): se añadió una introducción guiada antes de las tres perspectivas, se renombró Admin a Administración, se mantuvo la traza cerrada por defecto con control accesible y se corrigió la mensajería de derivación por voz para no afirmar que se notificó a recepción. `landing/demo.html`, `landing/demo-console.css`, `landing/demo.js` y `landing/voice.js`; `git diff --check` pasó. El baseline Playwright de solo lectura antes del cambio falló como se esperaba: no había introducción, la etiqueta era Admin y la traza estaba abierta. Aún falta la verificación funcional/responsive; no se envió mensaje ni se creó reserva.

L17 (cache de recursos detectada en T4; T3 reabierta): el HTML nuevo se sirvió, pero `demo.js?v=20261107a` seguía usando un recurso cacheado por `public, max-age=31536000, immutable`, y el navegador mostró el comportamiento anterior. Un GET con `cache: no-store` confirmó que el servidor sí entrega el JS actualizado. Actualizar los parámetros de versión de `demo-console.css`, `demo.js` y `voice.js` y repetir la prueba. No se enviaron mensajes ni se crearon reservas.

L18 (T3 completada; T4 reanudada): se actualizó a `?v=20261108a` la URL inmutable de `demo-console.css`, `demo.js` y `voice.js` para que el navegador descargue los cambios. `git diff --check` pasó; las comprobaciones Playwright post-bust aún están pendientes.

L19 (T4 móvil; T3 reabierta): a 390×844 no hay desbordamiento horizontal, la historia precede a las pestañas y el teléfono va antes del panel de control. La captura mostró que la introducción ocupa ~597 px y el teléfono apenas asoma en el primer viewport. Compactar la lede y los pasos móviles, conservando las tres perspectivas y el aviso de derivación simulada. No se enviaron mensajes ni se crearon reservas.

L20 (refinamiento responsive T3): se acortó la lede y se dispusieron los tres pasos en una fila compacta solo en ≤620 px; se mantuvo el aviso y la introducción. El HTML referencia `demo-console.css?v=20261108b` para evitar el caché inmutable previo. `git diff --check` pasó. T4 debe repetir la captura y medir el primer viewport; no hubo cambios de datos.

L21 (verificación UI T4): con `demo-console.css?v=20261108b`, `demo.js?v=20261108a` y `voice.js?v=20261108a`, la jerarquía, las tres pestañas, el estado inicial de la traza y la relación ARIA pasan. Clics en Recepción/Admin/Huésped muestran el panel correcto; la traza abre/cierra y no se envió ningún mensaje (0 mensajes de huésped). Playwright a 320, 390, 768, 1024 y 1920 px: sin overflow horizontal, pestañas caben y teléfono precede controles según breakpoint. A 390×844, introducción 328 px y 317 px del teléfono visibles. Snapshot accesible muestra h1, tablist con nombres y tabpanel. Falta verificar el texto de voz servido; no se probó el turno de voz ni acciones del PMS.

L22 (T4 cerrada; T5 en curso): el GET de `voice.js?v=20261108a` respondió 200 e incluye “Derivación simulada: no se notificó a recepción”, sin el texto anterior que afirmaba un aviso. `http://localhost:8080/demo` y la vista Recepción/Admin se abrieron en contexto Playwright aislado; el iframe Admin quedó presente, pero no se operó. No se enviaron mensajes de huésped ni de voz, no se crearon reservas y no se modificaron datos operativos. La suite Python sigue sin poder recopilarse por el intento anterior con exit 127; no se repitió.
