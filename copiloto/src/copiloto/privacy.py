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
<style>
  :root {{ --bg:#f6f0e6; --ink:#2f2418; --accent:#8c6a3f; --card:#fffaf2; --line:#e3d6c0; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#1d1812; --ink:#efe5d3; --accent:#d1a971; --card:#272017; --line:#3b3226; }}
  }}
  body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.6 system-ui, sans-serif; }}
  main {{ max-width:720px; margin:0 auto; padding:24px 16px 64px; }}
  h1 {{ font-size:1.6rem; }} h2 {{ font-size:1.1rem; margin-top:2rem; color:var(--accent); }}
  .draft {{ background:var(--card); border:1px solid var(--line); border-left:4px solid var(--accent);
           padding:12px 16px; border-radius:6px; }}
  a {{ color:var(--accent); }}
</style>
</head>
<body>
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
        ai_paragraph=escape(paragraph),
        hotel=escape(hotel.hotel["name"]),
        contact=escape(hotel.privacy["responsible_contact"]),
        # La retención publicada es la misma que aplica la purga (una sola fuente de verdad).
        retention=int(retention_days if retention_days is not None else hotel.privacy["retention_days"]),
    )
