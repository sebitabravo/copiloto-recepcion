# Costos

## Prototipo: $0

| Componente | Costo | Nota |
|---|---|---|
| Chatwoot Community `v4.18.0-ce` | $0 | Licencia MIT, autoalojado |
| Dashboard Apps de Chatwoot | $0 | Están en el núcleo OSS (`app/models/dashboard_app.rb`) |
| Widget web | $0 | Canal base de la demo |
| copiloto, pms_mock | $0 | Python, FastAPI, SQLite |
| LLM | $0 sin IA; con IA, pago por uso | Sin `LLM_API_KEY` el bot es determinista. Con DeepSeek se paga por token (precios en https://api-docs.deepseek.com/quick_start/pricing, no verificados aquí). Una conversación de reserva completa usó unos 2.500 tokens en la prueba. Los topes de la demo acotan el gasto |
| Telegram | $0 | Con Quick Tunnel de Cloudflare |
| WhatsApp Cloud API | $0 hasta 1.000 mensajes de servicio al mes por número | Sin método de pago no entrega al agotarse |

## Escenario real (EVA2)

Costo fijo referencial de **90.000 CLP al mes** (infraestructura y mantención) más **M**, la parte variable
(mensajes de WhatsApp sobre la cuota gratuita). El copiloto calcula el **costo por consulta** como
`(FIXED_MONTHLY_CLP + USAGE_M_CLP) / consultas` y lo muestra en `/metricas`; ajusta ambos valores por
entorno.

La cifra de 90.000 CLP es un supuesto de EVA2, no una cotización. Cuando se integre el PMS real puede sumarse
el costo de la integración que defina el proveedor.
