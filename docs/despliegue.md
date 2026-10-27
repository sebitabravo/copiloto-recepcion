# Despliegue

## Local (demo)

```bash
make up && make creds
```

Requiere Docker con 4 GB o más. Si Chatwoot no arranca por falta de memoria con OrbStack, sube el límite:
`orb config set memory_mib 8192` (reinicia la VM de Docker, así que detiene otros contenedores).

El stack se define en `infra/docker-compose.yml` con imágenes fijadas: `chatwoot/chatwoot:v4.18.0-ce`,
`pgvector/pgvector:pg16`, `redis:7-alpine`, `nginx:alpine`. `make up` es idempotente: puedes repetirlo.

## Red

Los puertos se publican solo en `127.0.0.1`. Para mostrar la demo a otros equipos de tu red define
`BIND_ADDR=0.0.0.0` antes de `make up`; en ese caso protege el panel y las métricas (ver «Servidor»).

## Variables

Se generan en `.env` (gitignored) a partir de `.env.example`. Las de Chatwoot (tokens, ids) las escribe el seed
en `.env.runtime` (gitignored). Nunca las commitees.

| Variable | Uso |
|---|---|
| `WEBHOOK_SECRET` | Firma HMAC del webhook de Chatwoot y secreto del webhook del PMS |
| `STAFF_TOKEN` | Token que usa recepción en el PMS simulado |
| `SHIFT_START` / `SHIFT_END` | Turno humano (hora de `America/Santiago`) |
| `FIXED_MONTHLY_CLP` | Costo fijo mensual para el costo por consulta |

## Servidor

1. Una VM con 4 GB de RAM y Docker. Copia el repo, corre `make up`.
2. Pon un proxy con HTTPS delante (Caddy o nginx) y define `FRONTEND_URL` con la URL pública de Chatwoot.
3. **Protege `/panel`, `/api/panel/*` y `/metricas*` del copiloto con login en el proxy**: no tienen
   autenticación propia y muestran nombres y fechas de huéspedes. Expón solo `/webhooks/*` y `/privacidad`
   sin login.
4. Cambia la URL del Dashboard App en Chatwoot (Configuración → Integraciones → Dashboard Apps) a la URL
   pública del panel, y `PMS_STAFF_URL` a la del PMS.
5. Respalda los volúmenes `pg_data` y `copiloto_data`.

## Del PMS simulado al real

Implementa `PxsolAdapter` (`copiloto/src/copiloto/pms.py`) con la misma firma que `MockPxsolAdapter`: lectura
de solo consulta con sello de hora. Necesita credenciales del hotel y el contrato del proveedor. La
confirmación sigue siendo humana.
