# Privacidad y Ley 21.719

El aviso que ve el huésped está en `/privacidad` del copiloto (borrador para revisión del hotel). Este
documento resume cómo se aplica en el diseño. No reemplaza la revisión de un abogado.

| Principio | Cómo se cumple |
|---|---|
| Datos mínimos | Solo texto del chat, nombre del canal, fechas y número de huéspedes. No se pide RUT, pago, correo ni teléfono (el correo está desactivado en la bandeja web) |
| Finalidad | Orientar la consulta y derivar a recepción; el bot no decide ni confirma reservas |
| Idempotencia | Cada mensaje de Chatwoot se procesa una sola vez (`processed_messages`) |
| Retención | 90 días (por validar con el hotel): el copiloto borra estados y pre-reservas vencidos y deja los eventos sin texto, con identificadores seudonimizados (hash irreversible), solo como contadores |
| Terceros de IA | Sin `LLM_API_KEY` no hay LLM y ningún mensaje sale. Con IA, el texto va a un proveedor externo (DeepSeek en la demo): solo datos ficticios, y el aviso de privacidad lo informa. Evaluar la Ley 21.719 (transferencia internacional) antes de datos reales |
| Derechos | Contacto del responsable: comercial@hotelbordeluz.cl |

## Pendiente

- La retención del lado de **Chatwoot** (conversaciones y contactos) no la gestiona el copiloto: bórralas
  desde Chatwoot o con una tarea propia según la política que defina el hotel.
- Validar plazos, base legal y responsable con el hotel antes de usar datos reales.
- Los datos de la demo son ficticios.
