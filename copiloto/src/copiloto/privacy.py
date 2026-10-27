"""Aviso de privacidad (borrador para revisión del hotel), conforme al diseño de EVA2 y a la Ley 21.719."""

from html import escape

from copiloto.hotel import HotelData

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
No es el sitio oficial de {hotel}. Todos los datos de la demostración son ficticios.</p>

<h2>Quién es el responsable</h2>
<p>{hotel}. Contacto para consultas y ejercicio de derechos:
<a href="mailto:{contact}">{contact}</a>.</p>

<h2>Para qué usamos tus datos (finalidad)</h2>
<p>Orientar tu consulta, mostrarte información del hotel y, si lo pides, derivar tu solicitud de
disponibilidad a una persona de recepción. El asistente no confirma reservas: solo las deja
como pre-información y recepción las valida.</p>

<h2>Qué datos tratamos (datos mínimos)</h2>
<ul>
<li>El texto de tus mensajes y el nombre que muestre tu canal de chat.</li>
<li>Fechas de estadía y cantidad de adultos y niños, si los entregas.</li>
</ul>
<p>No pedimos RUT, datos de pago, correo ni teléfono dentro del chat.</p>

<h2>Cuánto tiempo los guardamos (retención)</h2>
<p>El asistente borra su estado de conversación y las pre-reservas auxiliares {retention} días después de tu
último mensaje (valor sujeto a validación del hotel) y deja solo contadores sin texto ni identificadores
enlazables. Las conversaciones guardadas en la bandeja de recepción se eliminan según la política del hotel.</p>

<h2>Con quién se comparten</h2>
<p>Con el equipo de recepción del hotel. El asistente funciona sin inteligencia artificial generativa
y no envía tus mensajes a terceros para analizarlos.</p>

<h2>Tus derechos</h2>
<p>Puedes pedir acceso, rectificación, supresión, oposición, bloqueo y portabilidad de tus datos
escribiendo a <a href="mailto:{contact}">{contact}</a>.</p>
</main>
</body>
</html>
"""


def render(hotel: HotelData) -> str:
    return PAGE.format(
        hotel=escape(hotel.hotel["name"]),
        contact=escape(hotel.privacy["responsible_contact"]),
        retention=int(hotel.privacy["retention_days"]),
    )
