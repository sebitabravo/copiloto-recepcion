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
| T1 | Sincronizar `design/system.md` y `design/system.html` con las fuentes visuales actuales | Delegado: `gentle-ai-worker` (context backstop; superficies exactas en el handoff) | S2, S4 | in_progress: validado; commit pendiente | Plan: `docs(design): refresh current design system` |
| T2 | Crear tres direcciones visuales distintas para `/demo` y elegir la que mejor cuenta el valor del proyecto | Padre con Gentle Design | S1, S2, S5 | pending | Plan: `design(demo): add guided demo directions` |
| T3 | Implementar la dirección elegida en la ruta de demo conservando las capacidades existentes | Padre, inline | S1, S2, S3, S5 | pending | Plan: `feat(demo): clarify product story and role views` |
| T4 | Verificar interacciones, accesibilidad y adaptación de la demo; registrar cualquier runner no disponible | Padre | S3 | pending | Sin commit |
| T5 | Cerrar unidades revisadas, registrar commits y comunicar resultado y límites | Padre | S1–S4 | pending | Pendiente |

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
