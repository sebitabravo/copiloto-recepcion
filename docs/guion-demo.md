# Guion de la demo en vivo

Para la presentación del miércoles. Cinco minutos de recorrido, con los respaldos ya previstos.

## Un día antes

```bash
make up            # stack completo y healthchecks
make seed          # idempotente: usuarios, bandeja, etiquetas, equipo
make test          # 428 pruebas
uv run --with httpx --with tzdata python scripts/e2e.py   # 4 casos reales
make creds         # usuarios demo y token del PMS
```

Si `e2e` falla, no se presenta: primero se arregla. El e2e cubre los cuatro casos que se van a mostrar
(FAQ, disponibilidad, fuera de turno, PMS caído).

Si quieres empezar con la cola vacía (las pruebas dejan conversaciones con esperas de horas), corre
`make reset` **antes** de `make up`; borra volúmenes y vuelve a sembrar. Es destructivo para los datos de
la demo, no para el código.

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

## Guion (5 minutos)

| Momento | Qué haces | Qué se ve |
| --- | --- | --- |
| 1. Portada | Recorres la página hasta el CTA | Hero compuesto, cifras con contexto, recorrido de cinco pasos, pantallas de recepción y límites declarados |
| 2. Huésped | "Probar la demo" → pestaña Huésped → escribes **hola** | Aviso de privacidad primero y **ubicación** antes de cualquier pregunta |
| 3. Consulta | **¿tienen piscina?** y luego **quiero reservar** con fechas y 2 adultos | Respuesta en segundos y «Disponible según lectura del PMS a las HH:MM · pendiente de confirmación» |
| 4. Recepción | Pestaña Recepción | La conversación llega con nota privada, etiqueta comercial y cronómetro de SLA (verde → ámbar 120 s → rojo 180 s) |
| 5. Confirmación | Panel → **Confirmar en el PMS** → token de personal | Reserva creada; vuelves a la pestaña Admin y está en el PMS y en las métricas |
| 6. Canal real | Botón **Escribir a recepción** | Widget real de Chatwoot, misma respuesta del copiloto, misma bandeja |
| 7. Cierre | Métricas | Conversión, cumplimiento < 180 s y costo por consulta |

Frase de cierre sugerida: «El copiloto propone y recepción confirma; el bot no cierra reservas solo».

## Si algo falla

| Síntoma | Qué hacer | Qué decir |
| --- | --- | --- |
| El copiloto responde con el menú guiado | Es el comportamiento sin `LLM_API_KEY`, no un error | «Sin clave de modelo, el flujo guiado cubre lo mismo y no depende de internet» |
| «Recepción verificará cupos» | El PMS está caído o simulado caído (`SIMULATE_DOWN=1`) | «Cuando el PMS no responde, el bot no promete cupos: deriva» |
| Fuera de horario | `SHIFT_START`/`SHIFT_END` en `.env` | «El bot informa el horario real de recepción» |
| El widget no abre | Chatwoot no está arriba | «El canal de recepción está separado del simulador; ahora no está disponible» |
| No carga la consola | Revisa `/health` y `docker compose ps` | No improvises: `make up` y espera healthchecks |

## Qué responder si preguntan por el stack

- Front **estático** (HTML/CSS/JS) servido por nginx, con sistema de diseño y auditoría de calidad: decisión
  documentada en `docs/adr/0001-front-estatico.md`, con la migración a componentes planificada.
- API **FastAPI** con 428 pruebas, e2e de cuatro casos, contenedores sin root, solo lectura y `cap_drop`.
- **Modo demo por sesión de servidor**: el navegador nunca recibe credenciales; el token del PMS no se
  expone.
- Límites declarados: PMS real por contrato (sin API pública de Pxsol), WhatsApp no oficial y un solo
  proceso para esta demo.

## Después

```bash
make backup    # respaldo en caliente de Chatwoot y las bases SQLite
```
