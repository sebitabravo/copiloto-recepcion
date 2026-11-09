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
| Build estático (`staticDemo: true`) | Administración/PMS se declara no disponible. No hay peticiones al PMS, iframe activo ni reservas creadas o guardadas desde esta vista. |
| Sin URL válida de PMS | Aviso de servicio no configurado; no se intenta abrir una sesión. No se aceptan URLs con credenciales, query o fragmento. |
| PMS inaccesible | Aviso y **Reintentar conexión**, sin inventar habitaciones ni reservas. La comprobación tiene un plazo de 5 segundos. |
| PMS accesible | Se ofrece apertura explícita. La sonda `no-cors` solo comprueba conectividad: no certifica que el modo demo esté habilitado. El servidor puede rechazar `/admin?demo=1`. |

El PMS es un servicio de prueba **separado**: sus reservas no comparten el aislamiento por corrida del chat ni confirman automáticamente sus solicitudes. Usa solo datos ficticios. La página no interpreta una carga del iframe como confirmación de autenticación o de escritura.

## Verificación de esta entrega

`node --test scripts/test-demo-split.mjs`: **17/17**. Cubre el selector, la indisponibilidad estática, configuración inválida, conectividad/error/reintento y conservación de los controles de huésped/recepción con red controlada. RED inicial: **12/17**, cinco fallos por Administración ausente. `node --check landing/demo-page.js` y `node --check landing/demo-admin.js`: sin errores. No certifica escrituras reales ni integración PMS.

Playwright comprobó la vista en escritorio y móvil (390×844): el panel quedó dentro del viewport y la sonda de `/health` devolvió 200. No se abrió el iframe ni se creó o confirmó una reserva. Los errores CORS de `/api/demo/status` correspondieron al origen de prueba (`127.0.0.1:8765`) frente a la API configurada en `localhost:8100`. El selector puede ocupar varias filas en pantallas estrechas; no es una matriz responsive completa ni una prueba de contraste/lector de pantalla. La respuesta de salud tampoco certifica autenticación ni `DEMO_MODE`; el PMS real puede rechazar el acceso.
