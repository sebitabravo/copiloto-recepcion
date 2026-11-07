"""Aviso de privacidad del prototipo, pendiente de revisión del hotel y revisión legal."""

from html import escape

from copiloto.hotel import HotelData
from copiloto.textutil import is_local_url

PAGE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aviso de privacidad · Copiloto de Recepción</title>
<link rel="icon" href="{favicon}">
<link rel="stylesheet" href="/static/theme.css">
<style>
  body {{ font-size:16px; line-height:1.7; }}
  .site {{ border-bottom:1px solid var(--line); background:color-mix(in oklab, var(--bg) 88%, transparent); }}
  .site-inner {{ max-width:720px; margin:0 auto; padding:14px 20px; display:flex; align-items:center;
                justify-content:space-between; gap:12px; flex-wrap:wrap; }}
  .brand {{ display:inline-flex; align-items:center; gap:10px; color:var(--ink); text-decoration:none;
           font-weight:650; letter-spacing:-.01em; min-height:44px; }}
  .brand-tag {{ color:var(--muted); font-weight:500; font-size:.82rem; padding-left:10px;
               border-left:1px solid var(--line); }}
  .brand-mark {{ width:30px; height:30px; display:grid; place-items:center; border-radius:9px;
                color:var(--accent-ink); font:400 1.15rem/1 var(--font-display);
                background:linear-gradient(160deg, color-mix(in oklab, var(--accent) 88%, #fff), var(--accent)); }}
  .back {{ color:var(--accent); font-weight:600; font-size:.92rem; min-height:44px; display:inline-flex;
          align-items:center; }}
  main {{ max-width:720px; margin:0 auto; padding:40px 20px 72px; }}
  h1 {{ font-size:clamp(2.2rem, 5vw, 3rem); line-height:1.05; letter-spacing:-.02em; margin:0 0 1.2rem; }}
  h2 {{ font-size:1.55rem; line-height:1.15; letter-spacing:-.015em; margin:2.4rem 0 .6rem; }}
  p, li {{ max-width:68ch; color:var(--ink-2); }}
  .draft {{ background:var(--card); border:1px solid var(--line); border-left:3px solid var(--accent);
           padding:14px 18px; border-radius:12px; color:var(--ink); box-shadow:var(--shadow); }}
  a {{ color:var(--accent); }}
  :focus-visible {{ outline:3px solid var(--accent); outline-offset:3px; border-radius:4px; }}
</style>
</head>
<body>
<header class="site">
<div class="site-inner">
<a class="brand" href="{home}"><span class="brand-mark" aria-hidden="true">B</span>Bordeluz
<span class="brand-tag">Copiloto de recepción</span></a>
<a class="back" href="{home}">← Volver a la portada</a>
</div>
</header>
<main>
<h1>Aviso de privacidad</h1>
<p class="draft"><strong>Borrador para revisión del hotel.</strong> Prototipo académico INNOVA3 · INACAP.
No es el sitio oficial de {hotel}. Usa solo datos ficticios. Este borrador no constituye una certificación legal.</p>

<h2>Quién es el responsable</h2>
<p>{hotel}. Contacto para consultas y ejercicio de derechos:
<a href="mailto:{contact}">{contact}</a>.</p>

<h2>Para qué usamos tus datos (finalidad)</h2>
<p>Orientar tu consulta y mostrar información del hotel. En modo completo, si el servidor habilita la reserva
autónoma, la demo puede crear una reserva en el PMS simulado después de mostrar una propuesta y recibir tu
confirmación explícita. Los modos asistido y de voz no crean reservas autónomas. El flujo sin IA responde
información del hotel, sin consultar disponibilidad.</p>
<p>La derivación del simulador no notifica a recepción. El widget separado de Chatwoot sí envía la conversación
a su bandeja cuando está configurado y conectado. Reiniciar el historial no elimina reservas del PMS.</p>

<h2>Qué datos tratamos (datos mínimos)</h2>
<ul>
<li>El texto de tus mensajes y el nombre que muestre tu canal de chat.</li>
<li>Fechas de estadía y cantidad de adultos y niños, si los entregas.</li>
<li>Nombre ficticio del huésped y habitación elegida para una propuesta de reserva de demostración.</li>
</ul>
<p>No pedimos RUT, datos de pago, correo ni teléfono dentro del chat.</p>

<h2>Cuánto tiempo los guardamos (retención)</h2>
<p>El asistente borra su estado de conversación y las pre-reservas auxiliares {retention} días después de tu
último mensaje (valor sujeto a validación del hotel) y deja solo contadores sin texto ni identificadores
enlazables. Las conversaciones guardadas en la bandeja de recepción se eliminan según la política del hotel.</p>

<h2>Con quién se comparten</h2>
<p>Con el equipo de recepción del hotel. {ai_paragraph}</p>

<h2>Tus derechos</h2>
<p>Puedes pedir acceso, rectificación, supresión, oposición, bloqueo y portabilidad de tus datos
escribiendo a <a href="mailto:{contact}">{contact}</a>.</p>
</main>
</body>
</html>
"""


# El mismo monograma que el panel y las métricas, en línea: la página no depende de otro archivo.
FAVICON = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
    "%3Crect width='32' height='32' rx='9' fill='%238d5a2b'/%3E%3Ctext x='16' y='23' "
    "font-family='Georgia,serif' font-size='19' fill='%23fff8ef' text-anchor='middle'%3EB%3C/text%3E%3C/svg%3E"
)

AI_OFF = (
    "El flujo sin IA no envía mensajes a un modelo generativo. El canal separado de recepción usa Chatwoot; "
    "si usas voz, se aplica también el tratamiento indicado para ese canal."
)
AI_ON = (
    "El asistente usa un modelo de lenguaje de un tercero ({provider}) para entender tus mensajes: el texto "
    "de cada mensaje y los datos de tu consulta viajan a ese proveedor, que puede estar fuera de Chile. "
    "Por eso no debes escribir datos personales reales: esta demostración usa datos ficticios. Guardamos "
    "un historial acotado de la conversación solo para que el asistente mantenga el hilo, y se borra con la "
    "retención."
)


AI_LOCAL = (
    "El asistente usa un modelo de lenguaje que se ejecuta en la misma infraestructura del hotel "
    "({provider}): por este tratamiento, tus mensajes no se envían a proveedores externos. Aun así, esta "
    "demostración usa datos ficticios: no escribas datos personales reales. Guardamos un historial acotado "
    "de la conversación solo para que el asistente mantenga el hilo, y se borra con la retención."
)

VOICE_ON = (
    "Si usas la demo de voz, el audio de tu micrófono lo transcribe el navegador (en Chrome, con el servicio "
    "de reconocimiento de voz de Google) y el texto de cada respuesta se envía a ElevenLabs para generar "
    "la voz. No guardamos el audio."
)


def render(
    hotel: HotelData,
    ai_provider: str | None = None,
    ai_base_url: str = "",
    voice: bool = False,
    retention_days: int | None = None,
    home_url: str = "/",
) -> str:
    if not ai_provider:
        paragraph = AI_OFF
    elif is_local_url(ai_base_url):
        paragraph = AI_LOCAL.format(provider=ai_provider)
    else:
        paragraph = AI_ON.format(provider=ai_provider)
    if voice:
        paragraph = f"{paragraph} {VOICE_ON}"
    return PAGE.format(
        home=escape(home_url) or "/",
        favicon=FAVICON,
        ai_paragraph=escape(paragraph),
        hotel=escape(hotel.hotel["name"]),
        contact=escape(hotel.privacy["responsible_contact"]),
        # La retención publicada es la misma que aplica la purga (una sola fuente de verdad).
        retention=int(retention_days if retention_days is not None else hotel.privacy["retention_days"]),
    )
