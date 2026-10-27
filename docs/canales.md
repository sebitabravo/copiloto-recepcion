# Canales

El canal base de la demo es el **widget web**: no depende de terceros y cuesta $0. Telegram y WhatsApp son
opcionales; en ambos el bot manda las opciones como **lista numerada** («Responde con el número»).

## Telegram (gratis, en un teléfono real)

Chatwoot registra el webhook de Telegram con `FRONTEND_URL`, así que necesita una URL HTTPS pública.

1. En Telegram habla con **@BotFather**, crea un bot y copia el token.
2. `./scripts/tunnel.sh` (Quick Tunnel de Cloudflare vía Docker con tag fijado) y copia la URL
   `https://xxxx.trycloudflare.com`. La URL cambia cada vez; deja la terminal abierta. **El túnel expone Chatwoot completo (login y API) a
   internet**: úsalo solo durante la prueba, con la contraseña demo fuerte, y ciérralo al terminar.
3. En otra terminal: `FRONTEND_URL=https://xxxx.trycloudflare.com docker compose -f infra/docker-compose.yml
   --project-directory . up -d chatwoot sidekiq`.
4. En Chatwoot: Configuración → Bandejas → Agregar → **Telegram**, pega el token.
5. En esa bandeja, pestaña *Configuración de bot*, selecciona **Copiloto de Recepción**.
6. Escríbele al bot desde tu teléfono.

Para volver al modo local: `docker compose ... up -d chatwoot sidekiq` sin `FRONTEND_URL`.

## WhatsApp Cloud API

Necesita un login humano en Meta; no se automatiza.

1. Crea una app en https://developers.facebook.com con el producto WhatsApp y usa el **número de prueba**
   que entrega Meta. **Nunca conectes el número real del hotel (+56 963949710) a esta demo.**
2. Con el túnel de arriba activo, en Chatwoot crea una bandeja **WhatsApp Cloud** con el phone number ID, el
   business account ID y el token de la app; Chatwoot muestra la URL del webhook y el verify token para
   pegarlos en Meta.
3. Asigna el bot a la bandeja como en Telegram.

Límites verificados al armar el plan (revisa las tarifas vigentes de Meta antes de usarlo):
- Desde el 1-oct-2026 Meta cobra los mensajes de servicio, pero cada número tiene **1.000 mensajes de
  servicio gratis al mes**; sin método de pago, deja de entregar al agotarse.
- Por eso WhatsApp queda fuera del camino crítico de la demo.
