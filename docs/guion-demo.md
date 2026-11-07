# Guion de la demo en vivo

Para la presentación del miércoles. Cinco minutos de recorrido, con los respaldos ya previstos.

## Un día antes

```bash
./scripts/demo.sh up      # stack completo y healthchecks (o `make up` si tienes make)
./scripts/demo.sh seed    # idempotente: usuarios, bandeja, etiquetas, equipo
./scripts/demo.sh test    # 447 pruebas
./scripts/demo.sh e2e     # 4 casos reales contra el stack
./scripts/demo.sh creds   # usuarios demo y token del PMS
```

Si `e2e` falla, no se presenta: primero se arregla. El e2e cubre los cuatro casos que se van a mostrar
(FAQ, disponibilidad, fuera de turno, PMS caído).

Si quieres empezar con la cola vacía (las pruebas dejan conversaciones con esperas de horas), corre
`./scripts/demo.sh reset` **antes** de `./scripts/demo.sh up`; borra volúmenes y vuelve a sembrar. Es
destructivo para los datos de la demo, no para el código.

Dos notas de operación:

- Si cambias `infra/landing/nginx.conf`, vuelve a levantar el stack (`./scripts/demo.sh up` o `make up`):
  ambos reinician el contenedor `landing` al final, y nginx lee su configuración al arrancar. Sin ese
  reinicio, un stack ya levantado sigue con la configuración vieja y `/demo` responde 404.
- `landing/config.js` solo existe después del seed (`./scripts/demo.sh seed`): lo genera `scripts/seed-chatwoot.sh`.
  Sin ese archivo el widget de Chatwoot no carga y el enlace de privacidad cae a su valor por defecto.

## Treinta minutos antes

1. `./scripts/preflight.sh` — verifica los servicios y (si corresponde) el modelo local.
2. Deja abiertas estas pestañas, en este orden:
   - `http://localhost:8080` — portada.
   - `http://localhost:8080/demo` — consola de demo (pestaña Huésped).
   - `http://localhost:8100/panel` — panel de recepción.
   - `http://localhost:3000` — bandeja de Chatwoot.
   - `http://localhost:8200/admin` — PMS simulado.
   - `http://localhost:8100/metricas` — métricas del piloto.
3. Comprueba que el **Modo demo** de la consola esté encendido: debe entrar sola a Recepción y a Admin,
   sin pedir credenciales. Si aparece "Sin sesión", el backend tiene la demo apagada (`DEMO_ENABLED`).
4. Baja el zoom del navegador a 90 % para que entren las tres columnas en el proyector.

## IA local (opcional)

El modelo corre en Docker (llama.cpp + Qwen2.5-3B) y no cuesta por consulta:

```bash
./scripts/demo.sh ia       # baja el modelo la primera vez (~2 GB) y reconecta el copiloto
./scripts/demo.sh ia-off   # vuelve al flujo guiado determinista
```

Medido en este equipo: **38 s** el primer turno (el servidor arma la caché del prompt) y **3-8 s**
en caliente. El modelo acierta ubicación y consultas con herramienta, pero **se equivoca en preguntas
frecuentes aprobadas** y no interpreta fechas en lenguaje natural.

Por eso: el recorrido del miércoles va con el **flujo guiado** (correcto y rápido, validado por el e2e).
Si quieres mostrar la IA, calienta el modelo con una pregunta de ubicación antes de presentar y evita
las de disponibilidad.

## La consola, en tres perspectivas

`/demo` abre en **Huésped**; las pestañas de arriba cambian de perspectiva sin salir de la página:

- **Huésped**: el chat tipo WhatsApp y, debajo, la traza de lo que hizo el asistente.
- **Recepción**: la cola real con espera y riesgo de SLA (solo lectura).
- **Admin**: el PMS simulado y el enlace a métricas, con el modo demo resolviendo el acceso.

El **icono de llamada** de la cabecera del teléfono abre una llamada dentro del teléfono: estado,
cronómetro, transcripción y colgar. Si el navegador no reconoce voz, la misma pantalla ofrece escribir.

## Guion (5 minutos)

| Momento | Qué haces | Qué se ve |
| --- | --- | --- |
| 1. Portada | Recorres la página hasta el CTA | Hero compuesto, cifras con contexto, recorrido de cinco pasos, pantallas de recepción y límites declarados |
| 2. Huésped | "Probar la demo" → pestaña Huésped → escribes **hola** | Aviso de privacidad primero y **ubicación** antes de cualquier pregunta |
| 3. Consulta | **¿tienen piscina?** y luego **quiero reservar** con fechas y 2 adultos | Respuesta en segundos y «Disponible según lectura del PMS a las HH:MM · pendiente de confirmación» |
| 4. Canal real | En la consola, botón **Escribir a recepción** → envías **quiero reservar** | Widget real de Chatwoot: misma respuesta del copiloto, pero esta conversación sí entra al sistema |
| 5. Recepción | Pestaña Recepción (y bandeja en http://localhost:3000) | La conversación del canal real llega con nota privada, etiqueta comercial y cronómetro de SLA (verde → ámbar 120 s → rojo 180 s) |
| 6. Confirmación | Panel → **Confirmar en el PMS** → token de personal | Reserva creada; vuelves a la pestaña Admin y está en el PMS y en las métricas |
| 7. Cierre | Métricas | Conversión, cumplimiento < 180 s y costo por consulta |

Los turnos del simulador (momentos 2 y 3) **no aparecen** en la pestaña Recepción ni en la bandeja de
Chatwoot: el simulador no crea conversaciones. Lo que ve recepción —cola, nota, etiqueta y cronómetro—
es solo la conversación del canal real del widget.

Frase de cierre sugerida: «El copiloto propone y recepción confirma; el bot no cierra reservas solo».

## Si algo falla

| Síntoma | Qué hacer | Qué decir |
| --- | --- | --- |
| El copiloto responde con el menú guiado | Es el comportamiento sin `LLM_API_KEY`, no un error | «Sin clave de modelo, el flujo guiado cubre lo mismo y no depende de internet» |
| «Recepción verificará cupos» | El PMS está caído o simulado caído (`SIMULATE_DOWN=1`) | «Cuando el PMS no responde, el bot no promete cupos: deriva» |
| Fuera de horario | `SHIFT_START`/`SHIFT_END` en `.env` | «El bot informa el horario real de recepción» |
| El widget no abre | Chatwoot no está arriba | «El canal de recepción está separado del simulador; ahora no está disponible» |
| No carga la consola | Revisa `/health` y `docker compose ps` | No improvises: `./scripts/demo.sh up` y espera healthchecks |

## Qué responder si preguntan por el stack

- Front **estático** (HTML/CSS/JS) servido por nginx, con sistema de diseño y auditoría de calidad: decisión
  documentada en `docs/adr/0001-front-estatico.md`, con la migración a componentes planificada.
- API **FastAPI** con 447 pruebas, e2e de cuatro casos, contenedores sin root, solo lectura y `cap_drop`.
- **Modo demo por sesión de servidor**: el navegador nunca recibe credenciales; el token del PMS no se
  expone.
- Límites declarados: PMS real por contrato (sin API pública de Pxsol), WhatsApp no oficial y un solo
  proceso para esta demo.

## Después

```bash
./scripts/backup.sh    # respaldo en caliente de Chatwoot y las bases SQLite (o `make backup`)
```
