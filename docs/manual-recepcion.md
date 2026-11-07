# Manual de recepción

Uso diario del Copiloto de Recepción desde Chatwoot (http://localhost:3000 en la demo).

## Qué ve recepción

- Las consultas simples (FAQ, ubicación, habitaciones) las atiende el bot y quedan en estado **Pendiente**.
  No hace falta intervenir.
- Cuando el huésped pide disponibilidad o hablar con una persona, la conversación pasa a **Abierta**, se
  asigna al equipo *recepción* y recibe la etiqueta `comercial`. Si fue fuera de turno, además `nocturna`.
- Cada traspaso trae una **nota privada «Pre-información del copiloto»** con huésped, fechas, huéspedes,
  habitación de interés, origen y la **lectura del PMS con su hora**. Esa lectura puede haber cambiado:
  revalídala en el PMS antes de responder.

## Cronómetro de 3 minutos

En la barra lateral derecha de la conversación abre la app **Copiloto**:

| Color | Significado |
|---|---|
| Verde | Menos de 120 s desde el traspaso |
| Ámbar | 120 s o más (etiqueta `sla-ambar`) |
| Rojo | 180 s o más (etiqueta `sla-vencido` y nota de alerta) |

El reloj arranca en el traspaso dentro del turno, **no se reinicia al asignar** y se detiene con tu primer
mensaje al huésped (las notas privadas no cuentan). Fuera de turno no corre.

## Cola de recepción

Sin una conversación abierta, el panel muestra la cola y el resumen del turno. Abierto en su propia pestaña
(http://localhost:8100/panel) usa todo el ancho: el resumen a la izquierda y la cola a la derecha; dentro de
Chatwoot queda en una columna.

- Los visitantes anónimos del widget, que Chatwoot nombra como `cool-mountain-791`, aparecen como
  **Visitante web · 791** (el número es el de Chatwoot).
- Las esperas de una hora o más se leen como `10 h 38 min`; las menores, como `2:15`.

## Confirmar una reserva

1. Pulsa **Confirmar en el PMS** en el panel. Se abre el PMS con los datos prellenados.
2. Revalida la disponibilidad, ingresa el token de personal y confirma.
3. El PMS avisa al copiloto (`booking_confirmed`): queda una nota en la conversación y la conversión entra
   a las métricas. El bot **nunca** confirma ni reserva.

La *pre-reserva auxiliar* del panel dura 15 minutos y vive solo en el copiloto: no bloquea el PMS ni lo toca
al vencer.

## Si algo falla

- **PMS caído**: el bot le dice al huésped que recepción verificará cupos y te traspasa igual. Revisa los
  cupos a mano.
- **El bot no responde**: mira `make logs`. Si Chatwoot no logra entregar el webhook mueve la conversación a
  *Abierta*, así que nunca queda un huésped sin atender.
- **Horario del turno**: se configura con `SHIFT_START` y `SHIFT_END` (default 08:00-22:00, por validar con
  el hotel).
