# /demo: huésped y recepción en el mismo hilo

La demo muestra una sola consulta desde dos roles. La portada (`index.html`) y su hoja (`demo.css`) no
cambian: `/demo` reutiliza sus tipografías, tokens, barra y pie, y agrega `demo-split.css`.

## Piezas

| Archivo | Rol |
|---|---|
| `demo.html` | Estructura: controles de presentación, chat del huésped y bandeja de recepción. |
| `demo-shared.js` | API con tiempo límite, llaves de idempotencia, formatos y render del hilo (sin `innerHTML`). |
| `demo-guest.js` | Chat «WhatsApp simulado»: atajos, respuestas sugeridas, reintento seguro y sondeo mientras recepción tiene el caso. |
| `demo-inbox.js` | Bandeja: lista con espera en vivo, hilo con notas internas y eventos, ficha del caso, tomar, responder, inventario, cerrar. |
| `demo-page.js` | Vistas (`?vista=huesped`, `?vista=recepcion` o partida) y escenario de turno de la sesión. |
| `static-demo.js` | Solo en la versión estática: servidor simulado en el navegador con el mismo contrato. |

## Reglas de la interfaz

- **Roles separados.** El chat del huésped usa solo su `session_id` y nunca envía cookies; la bandeja usa la
  sesión firmada de recepción. Con `?vista=huesped` la página no abre sesión de recepción.
- **Una fuente de verdad.** Todo lo que se ve sale del servidor (`/api/demo/conversation` y
  `/api/panel/requests`). Recargar muestra el mismo caso.
- **Quién habla.** Las burbujas dicen «Asistente virtual» o «Sofía · Recepción». Las notas internas solo se ven
  en la bandeja.
- **Acción principal según el estado.** «Tomar solicitud» si nadie la tomó; «Enviar respuesta» si la tomaste.
- **Color con texto.** Ámbar = pendiente, azul = en atención, verde = respondida, gris = cerrada; cada color va con
  su rótulo.
- **Reintentos.** Cada mensaje y cada respuesta llevan una llave; reintentar reenvía la misma y el servidor no
  duplica.

Contrato de la API: [docs/demo-api.md](../docs/demo-api.md). Guion: [docs/guion-demo.md](../docs/guion-demo.md).
