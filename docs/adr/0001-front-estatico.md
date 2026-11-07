# ADR 0001 · Front estático para la landing y la consola de demo

- **Estado:** aceptado
- **Fecha:** 2026-11-06
- **Contexto:** prototipo académico (INNOVA3 / EVA2) con demo en vivo

## Contexto

El producto tiene dos superficies web:

1. **Portada** (`/`): página de marketing con contenido fijo, animaciones y un CTA a la demo.
2. **Consola de demo** (`/demo`): simulador de conversación, trazas, guiones, voz y tres perspectivas
   (huésped, recepción, admin) con datos leídos de la API.

El resto del sistema es Python: FastAPI (`copiloto`), PMS simulado (`pms_mock`), puentes (`pms_bridge`,
`wa_bridge`), 447 pruebas, un e2e de cuatro casos y CI. La demo corre con Docker Compose y se muestra en
vivo, en plazos cortos, sin CDNs ni servicios externos: las tipografías y todo el CSS se sirven locales.

La pregunta que motiva este ADR es si corresponde reemplazar HTML/CSS/JS por un framework "más senior".

## Decisión

**Mantener el front como HTML, CSS y JavaScript propio, servido estáticamente por nginx**, con estas
condiciones de calidad:

- Un solo sistema de diseño documentado (`design/system.md`) con tokens extraídos de las fuentes reales.
- Pruebas de UI sobre el comportamiento del simulador (`scripts/test-demo-ui.mjs`, 14 casos) en CI.
- Presupuesto de accesibilidad y de peso verificado antes de cada entrega (ver `docs/calidad-front.md`).
- Sin dependencias de runtime en el navegador: ningún framework, ninguna librería de UI, ninguna fuente
  remota.
- La migración a un build con hashing y a componentes se planifica como fase 2 (ver abajo), no como
  requisito de esta entrega.

## Alternativas consideradas

| Alternativa | Por qué no ahora |
| --- | --- |
| **Next.js / React** | Aporta runtime, hidratación y un modelo mental de aplicación a una portada de contenido y a un simulador que ya funciona en JS propio. Es exactamente el "stack de moda" que no resuelve ningún problema de este producto y encarece la demo. |
| **Astro** | Es una elección correcta y probada para landings (la usa AgroVoz): contenido primero, cero JS por defecto, salida estática. Se adopta como **fase 2**, porque migrar portada y consola a componentes a días de una presentación cambia el riesgo de "se ve simple" por el riesgo de "no funciona en vivo". |
| **SPA (Vue/Svelte)** | Introduce router, estado y build para dos páginas; el simulador ya tiene su propia máquina de estados y sus pruebas. |
| **SSR desde FastAPI (Jinja)** | Mezcla la entrega de contenido con la API, obliga a reiniciar el backend para cambiar un texto y pierde el cacheado estático. |

## Consecuencias

**Positivas**

- La demo no depende de un build en el momento de mostrarla: lo que está en el árbol es lo que se sirve.
- El front es auditable de punta a punta: no hay cajas negras de framework ni JS inyectado.
- El contenido vive en HTML semántico, accesible y con `prefers-reduced-motion` respetado.
- El equipo puede explicar cada decisión técnica: tokens con origen, pruebas, presupuesto y límites.

**Negativas (aceptadas y medidas)**

- Hoy no hay minificación, bundling ni hashing de assets: el CSS ronda los 90 KB sin comprimir y nginx lo
  comprime en tránsito, pero el navegador no cachea por nombre único.
- `landing/demo.css` concentra los estilos de la portada y de la consola en un solo archivo.
- La falta de componentes obliga a duplicar pequeños bloques de HTML entre páginas.

## Fase 2 (después de la entrega)

1. **Build del front**: Vite o esbuild → assets con hash, minificados y con presupuesto de tamaño; nginx
   sirve `landing/dist` y `make up` construye antes de levantar. Criterio de aceptación: paridad visual,
   14/14 pruebas de UI y e2e en verde.
2. **Astro para la portada**: `index` como componentes (`Hero`, `Evidence`, `Pipeline`, `Shots`, `Limits`,
   `CTA`); la consola de demo permanece estática con sus módulos porque su valor es la interacción, no el
   contenido.
3. **Presupuesto en CI**: Lighthouse (performance y accesibilidad) y `axe-core` con umbrales escritos en
   `docs/calidad-front.md`.

## Referencias

- Sistema de diseño: `design/system.md`
- Calidad medida: `docs/calidad-front.md`
- Pruebas de UI: `scripts/test-demo-ui.mjs`
- Decisión hermana sobre la demo: `odd/tasks/landing-producto.md`
