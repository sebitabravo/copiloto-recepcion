# Administración dentro de `/demo`

El selector conserva **Vista partida**, **Huésped** y **Recepción**, y añade **Administración** sin cambiar la portada ni el flujo del chat. También se puede iniciar con `/demo?vista=admin`.

## Recorrido

1. Selecciona **Administración** con clic o con Tab y Enter/Espacio. El botón indica su estado con `aria-pressed` y referencia su panel con `aria-controls`.
2. Con el PMS de prueba configurado en `COPILOTO_CONFIG.pmsUrl`, la vista comprueba conectividad mediante un GET a `/health`, sin credenciales.
3. Pulsa **Abrir PMS de prueba**. El panel embebe la ruta existente `/admin?demo=1`; el servidor valida `DEMO_MODE` y crea su cookie HttpOnly. No se introducen ni se envían tokens desde el JavaScript de la demo.
4. Vuelve a **Vista partida**, **Huésped** o **Recepción**: se conservan los controles, el turno y la corrida del chat. Administración no inicia esos roles por su cuenta.

## Límites visibles

| Entorno | Resultado |
| --- | --- |
| Build estático (`staticDemo: true`) | El PMS se declara no disponible: sin peticiones, iframe ni reservas creadas o guardadas. El plano de ocupación (Recepción) y el dashboard (Administración) se muestran con datos simulados en el navegador, de solo lectura y relativos a hoy. |
| Sin URL válida de PMS | Aviso de servicio no configurado; no se intenta abrir una sesión. No se aceptan URLs con credenciales, query o fragmento. |
| PMS inaccesible | Aviso y **Reintentar conexión**, sin inventar habitaciones ni reservas. La comprobación tiene un plazo de 5 segundos. |
| PMS accesible | Se ofrece apertura explícita. La sonda `no-cors` solo comprueba conectividad: no certifica que el modo demo esté habilitado. El servidor puede rechazar `/admin?demo=1`. |

## Plano de ocupación y dashboard

Recepción tiene el conmutador «Solicitudes | Plano de ocupación» y Administración muestra un dashboard arriba. Los dos leen `GET /api/panel/occupancy?start=YYYY-MM-DD&days=14` (1 a 31 días), de solo lectura y con la sesión de recepción de la demo; sin sesión, Administración pide «Identificarse» con el diálogo «¿Quién atiende?».

| Entorno | Origen de los datos |
| --- | --- |
| Local (`make demo-local`) | El copiloto lee `GET /api/v1/occupancy` del PMS simulado con el token de personal. Las reservas que crea la IA en el chat aparecen como barras «IA». |
| Estático (Vercel) | `static-demo.js` responde la misma ruta con un set determinista relativo a hoy. Las reservas del chat no aparecen: ese chat solo lee cupos. |

El PMS es un servicio de prueba **separado**: sus reservas no comparten el aislamiento por corrida del chat ni confirman automáticamente sus solicitudes. Usa solo datos ficticios. La página no interpreta una carga del iframe como confirmación de autenticación o de escritura.

## Verificación de esta entrega

`node --test scripts/test-demo-split.mjs`: **17/17**. Cubre el selector, la indisponibilidad estática, configuración inválida, conectividad/error/reintento y conservación de los controles de huésped/recepción con red controlada. RED inicial: **12/17**, cinco fallos por Administración ausente. `node --check landing/demo-page.js` y `node --check landing/demo-admin.js`: sin errores. No certifica escrituras reales ni integración PMS.

Playwright comprobó la vista en escritorio y móvil (390×844): el panel quedó dentro del viewport y la sonda de `/health` devolvió 200. No se abrió el iframe ni se creó o confirmó una reserva. Los errores CORS de `/api/demo/status` correspondieron al origen de prueba (`127.0.0.1:8765`) frente a la API configurada en `localhost:8100`. El selector puede ocupar varias filas en pantallas estrechas; no es una matriz responsive completa ni una prueba de contraste/lector de pantalla. La respuesta de salud tampoco certifica autenticación ni `DEMO_MODE`; el PMS real puede rechazar el acceso.
