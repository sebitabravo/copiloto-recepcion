# Recorrido seguro del proyecto

Esta guía permite presentar el prototipo paso a paso sin confundir una simulación de conversación con
un canal conectado a recepción. Está dirigida a quien prepara su primera demostración del proyecto.

## Antes de empezar

1. Pide al responsable del entorno que prepare el stack local siguiendo [despliegue](despliegue.md).
   Se necesitan Docker, los servicios del proyecto y la configuración de la landing. Esta guía no ejecuta
   instalaciones, migraciones ni llamadas de pago.
2. Abre la landing en `http://localhost:8080`. Para información sin IA basta el servidor del copiloto;
   para consultas con IA debe estar configurado y disponible el modelo. Para disponibilidad se necesita el PMS.
3. Consulta **Estado del copiloto**: verifica proceso y SQLite, no garantiza que IA, PMS, Chatwoot o voz funcionen.
   Consulta **Modelo y límites** para conocer las capacidades. `full` es una configuración, no una autorización:
   `autonomous_booking` indica el permiso efectivo y `sandbox` identifica el destino simulado autorizado.
4. Usa solo datos ficticios. Nunca introduzcas documentos de identidad, pagos, credenciales ni datos reales
   de huéspedes. La demostración de voz puede enviar audio al servicio del navegador y texto a ElevenLabs.
5. Ten claro qué quieres mostrar: el simulador no necesita que abras Chatwoot; la bandeja y WhatsApp sí
   requieren servicios y configuración propios. Un fallo de un canal no demuestra que todos fallen.

## Simulador del navegador

1. En **Conversa con el copiloto**, pregunta «¿Cómo llego?» o «¿Tienen piscina?». El navegador envía el texto
   directamente a `/api/demo/chat`. No pasa por WhatsApp ni crea una conversación de Chatwoot.
2. Abre opcionalmente **Acciones del asistente**. Las tarjetas muestran herramientas y resultados, no el
   razonamiento interno del modelo. La IA puede equivocarse: contrasta fechas, ocupación y totales.
3. Si está habilitado, pulsa **Consultar disponibilidad · continuar manualmente**. El guion reúne intención
   de consulta, fechas y ocupación y se detiene. No selecciona habitaciones, no da un nombre y no confirma.
   Si falla una consulta, no interpretes el guion como una reserva completada.
4. Elige tú una habitación entre las opciones realmente ofrecidas y proporciona un nombre ficticio.
   Espera la **Propuesta de reserva · aún no creada**, visible en el chat incluso con las acciones ocultas.
5. Revisa nombre, habitación y código, entrada, salida, noches, adultos, niños, total y etiqueta de simulación.
   Si algo no coincide, escribe la corrección y solicita una propuesta nueva. El botón anterior deja de servir
   al enviar otro mensaje; una propuesta también puede caducar en el servidor.
6. Solo si deseas crear una reserva ficticia, pulsa **Sí, confirmo la reserva**. Es un turno nuevo iniciado
   por ti. El servidor vuelve a validar los datos y permisos; el botón por sí solo no autoriza una escritura.
   No anuncies éxito hasta recibir el comprobante `booking_created`. Sin comprobante, no des por creada la reserva.
7. En modo asistido, sin IA o con permisos de reserva deshabilitados, no prometas una reserva autónoma.
   El flujo sin IA responde información del hotel; no consulta el PMS. La voz tampoco crea reservas autónomas.
8. Prueba **Simular derivación a recepción**: muestra una intención de derivación, pero no notifica a nadie.
   Para enviar un mensaje al equipo, usa el widget separado descrito a continuación.
9. **Reiniciar historial** borra el hilo del simulador. No elimina reservas del PMS, conversaciones de Chatwoot
   ni el historial independiente de voz. No lo presentes como una limpieza de todos los datos.

## Widget conectado a Chatwoot

1. El responsable debe haber preparado Chatwoot, su bandeja, AgentBot y webhooks, además de configurar el
   widget de la landing. No copies ni muestres las credenciales en pantalla o en una presentación.
2. Pulsa **Probar en la bandeja real de recepción**. Solo entonces se carga el SDK del widget. Si no conecta,
   revisa la configuración con el responsable; no digas que recepción recibió el mensaje.
3. Escribe un mensaje ficticio en ese widget, no en el simulador. Comprueba su llegada en la bandeja
   de `http://localhost:3000` con una sesión de personal autorizada.
4. Sigue el flujo mostrado por el canal y revisa el contexto en recepción. Una derivación real puede requerir
   intervención del equipo; no garantiza disponibilidad inmediata. El historial del simulador no se transfiere.
5. Consulta el [manual de recepción](manual-recepcion.md) para la cola, la respuesta humana y el PMS.
   El modo asistido deja información para la revisión del personal, no una reserva autónoma.

## WhatsApp mediante OpenWA

1. Este canal es opcional y distinto del simulador visual y del widget. Requiere Chatwoot, el puente de
   WhatsApp, OpenWA y una sesión vinculada con un teléfono dedicado a pruebas.
2. El puente no oficial a WhatsApp ya no forma parte del repositorio; el canal real es Chatwoot.
   con riesgo de suspensión del número. No conectes el número real del hotel ni lo presentes como API oficial de Meta.
3. Solo con autorización del responsable, prepara el perfil y vincula el teléfono según esa guía.
   Los comandos de preparación no se ejecutaron como parte de esta guía.
4. Envía desde otro teléfono una consulta ficticia al número dedicado y comprueba la conversación en el inbox
   correspondiente de Chatwoot. Recorrido: WhatsApp → OpenWA → puente → Chatwoot → copiloto.
5. Comprueba también la recepción de la respuesta en el teléfono: que aparezca en Chatwoot no prueba su
   entrega por WhatsApp. No uses reservas reales ni prometas entrega garantizada.

## Cierre de la presentación

La ilustración del hero contiene ejemplos, no resultados medidos. **Actividad registrada de la demo** consulta
contadores reales del prototipo de los últimos siete días, no actividad hotelera real. Anota qué canal y modo
probaste, qué resultados observaste y qué quedó pendiente. Esta guía describe cómo operar el proyecto; no
afirma que su historia de desarrollo haya seguido Scrum, TDD ni una certificación de seguridad o cumplimiento.
