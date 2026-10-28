# Mercado: a quién se le vende esto

Documento de segmentación y evidencia. Cada afirmación sobre lo que le falta a un hotel viene de una
fuente pública, no de una suposición.

## Segmento

Hoteles independientes y pymes de alojamiento de 10 a 40 habitaciones, en Chile y Latinoamérica, que
venden por WhatsApp y no tienen departamento de tecnología.

Quedan fuera, por ahora: cadenas con PMS propio y equipos de TI, y alojamientos sin recepción
presencial (donde el problema es otro).

## Lo que reportan los hoteles

| Fuente | Qué dice |
|---|---|
| Moneypenny, 2026 — 2.000 empresas y 5.001 consumidores, 200 líderes de hospitalidad | **70% elige al negocio que responde primero**; solo 47% vuelve a insistir si no lo atienden. Las consultas fuera de horario son «oportunidades de reserva ocultas» |
| AHLA, Front Desk Feedback, feb 2026 — 246 hoteleros | Más de la mitad opera con **dotación insuficiente**; 42% reporta escasez de personal; el costo laboral es la segunda presión (65%) |
| AHLA, dic 2024 — 282 hoteleros | 65% con escasez de personal; **recepción es la segunda área más afectada (26%)**; 6 a 7 vacantes promedio por propiedad |
| StayCentral, State of Independent Hotels 2026 | Lo que los hoteles sacaron de la carga humana: **responder preguntas rutinarias de pre-reserva**, actualizar tarifas, perseguir abonos, auditoría nocturna. Las propiedades que automatizaron dos o más tareas reportaron menos rotación |
| Estudio de 142 hoteles en Santander, Colombia (2026) | 68,3% usa apps de mensajería como canal de reserva; **WhatsApp llega a 78,3% en hoteles de 1 a 10 habitaciones**; 24,2% de los ingresos pasa por chat. Ahorro medio por comisiones: US$3.600 en seis meses. **Barreras declaradas por los dueños: registro de las conversaciones y escalabilidad** |
| Agentik, LATAM 2026 | Entre **30% y 50% de los mensajes llegan fuera del horario de recepción** |
| Caso de una posada brasileña (2026) | **37 consultas de reserva entre 22:00 y 07:00 en un mes**, casi ninguna convertida; R$31.000 recuperados en 90 días al responder con WhatsApp + IA |

Dos cosas se repiten en todas las fuentes: la velocidad de respuesta decide la reserva, y la
recepción no alcanza a cubrir el horario.

## Qué significa para el producto

| Necesidad reportada | Cómo la cubre hoy el prototipo |
|---|---|
| Responder primero | Respuesta automática en 0,3 s en el flujo guiado; el copiloto consulta el PMS y contesta con datos reales |
| Fuera de horario | Captura nocturna con etiqueta `nocturna` y pre-reserva de 15 minutos |
| No perder la venta por sobreventa | La IA nunca confirma: lee disponibilidad y deja la solicitud a una persona |
| No inventar datos | Consulta antes de responder; una afirmación sin herramienta se reemplaza |
| Registro de las conversaciones | Cola con tiempos de espera, notas del turno y métricas por conversación |
| Escalabilidad del canal | Va del lado del servidor: el personal no carga más trabajo cuando sube el volumen |
| Handover de turno (lo que más piden las herramientas de front desk) | **Resumen del turno** en el panel: conversaciones, preguntas resueltas, derivaciones, capturas nocturnas y pre-reservas activas |
| Acceso del personal | **Login por cookie firmada con nombre**, para que una nota o una confirmación tengan dueño |

## Por qué alguien lo paga

El estudio colombiano pone el número: US$3.600 ahorrados en comisiones en seis meses para un hotel
que mueve parte de su venta por chat. Una sola reserva recuperada al mes cubre un servicio de
US$30 a US$60.

Los precios publicados de la competencia van de €99 a €319 al mes más instalación. Un modelo
autohospedado sin costo por consulta tiene margen para cobrar menos y aun así sostener soporte.

## Qué falta para venderlo

1. **Prueba con recepción real.** Todo lo anterior es literatura; el piloto es lo que convierte la
   cita en argumento.
2. **Conector del PMS del cliente.** Es el trabajo por instalación y lo que hay que cotizar.
3. **WhatsApp oficial.** La demo simula el canal; conectar el número requiere un proveedor.

## Fuentes

- [AHLA — Rising Cost, Staffing Challenges Persist](https://www.ahla.com/news/rising-cost-staffing-challenges-persist-hotels-travel-demand-expected-hold-steady)
- [Moneypenny — The hospitality experience gap](https://www.moneypenny.com/uk/resources/blog/the-hospitality-experience-gap/)
- [Guest Squad — Why hotels lose bookings after hours](https://guestsquad.com/resources/insights/why-hotels-miss-bookings-after-hours)
- [StayCentral — The State of Independent Hotels 2026](https://staycentral.co/resources/state-of-independent-hotels-2026)
- [Lucero Pinzón — Messaging-app direct booking in independent hotels, Colombia (2026)](https://www.tourismjournal.net/archives/2026/vol8issue2/PartA/8-8-15-585.pdf)
- [Agentik — Convertir consultas hoteleras con IA](https://agentik.lat/blog/convertir-consultas-hoteleras-ia/)
