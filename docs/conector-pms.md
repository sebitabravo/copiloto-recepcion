# Conector de PMS

El copiloto no habla con cada PMS: habla con **un contrato**. El hotel conecta su sistema a ese
contrato y el código no cambia. `HttpPmsAdapter` es el cliente que lo consume, y el servicio
`pms-mock` es la implementación de referencia.

Si el PMS del hotel no expone el contrato, se escribe un **puente** pequeño entre su API y este
contrato. El copiloto no se toca.

## Los dos endpoints

### `GET {PMS_URL}{PMS_AVAILABILITY_PATH}`

Consulta de solo lectura. Parámetros: `checkin`, `checkout` (AAAA-MM-DD), `adults`, `children`.

```json
{
  "read_at": "2026-10-28T15:00:00-03:00",
  "source": "pms-hotel",
  "simulated": false,
  "room_types": [
    {
      "code": "doble_con_jacuzzi",
      "name": "Habitación Doble con Jacuzzi",
      "max_adults": 2,
      "max_children": 1,
      "m2": 32,
      "available_units": 2,
      "nightly_price_clp": 80000
    }
  ]
}
```

| Campo | Regla |
|---|---|
| `read_at` | Fecha y hora de la lectura, ISO 8601 con zona. Es el sello que ve recepción: sin él, el copiloto no puede decir cuándo se consultó |
| `source` | Nombre del sistema que respondió |
| `simulated` | `true` si los datos no son reales. El panel lo muestra como etiqueta |
| `room_types[].code` | Identificador estable de la habitación. Es el que se usa al reservar |
| `room_types[].available_units` | Cupos libres. `0` es una respuesta válida: significa sin disponibilidad |
| `room_types[].nightly_price_clp` | Precio por noche en pesos. Si el hotel cobra en otra moneda, el puente convierte |

Un valor fuera de rango (precio negativo, cupos negativos, campo faltante) **no se corrige**: se
trata como PMS no disponible. Es preferible decir «no pude consultar» que mostrar un precio inventado.

### `POST {PMS_URL}{PMS_BOOKING_PATH}`

Escribe una reserva. Solo se usa en el modo de IA autónoma de la demostración; en el piloto la
confirmación es humana.

```json
{
  "guest_name": "Camila Rojas",
  "room_code": "doble_con_jacuzzi",
  "checkin": "2027-03-15",
  "checkout": "2027-03-18",
  "adults": 2,
  "children": 1,
  "conversation_id": 33,
  "source": "ia"
}
```

Cabecera de autorización: `{PMS_AUTH_HEADER}: {PMS_STAFF_TOKEN}`.

Respuesta esperada: `201` con `booking_id`, `room_code`, `checkin`, `checkout`.

## Errores

| Situación | Cómo la trata el copiloto |
|---|---|
| Timeout, conexión caída, 5xx | `PmsUnavailable`: no afirma disponibilidad y deriva a recepción |
| JSON inválido o fuera de contrato | `PmsUnavailable` |
| `409` o `422` al reservar | `PmsConflict`: explica que no hay cupo y ofrece alternativas |

El copiloto nunca convierte un error del PMS en una promesa.

## Configuración por hotel

| Variable | Ejemplo | Para qué |
|---|---|---|
| `PMS_URL` | `http://pms.hotel:9000` | Base del PMS o del puente |
| `PMS_ADAPTER` | `http` o `none` | `none` = hotel sin PMS: orienta y deriva, nunca promete cupos |
| `PMS_AVAILABILITY_PATH` | `/v2/rooms/availability` | Ruta de lectura, si el proveedor usa otra |
| `PMS_BOOKING_PATH` | `/v2/bookings` | Ruta de escritura |
| `PMS_AUTH_HEADER` | `Authorization` | Cabecera que espera el proveedor |
| `PMS_STAFF_TOKEN` | — | Credencial de escritura. Sin ella no hay reserva autónoma |
| `PMS_TIMEOUT_S` | `4` | Corte por lentitud; el copiloto prefiere derivar antes que colgarse |

## Incorporar un hotel: checklist

1. Pedir credenciales de **lectura** y, si habrá escritura, de reserva.
2. Confirmar los `code` de cada tipo de habitación y que sean estables.
3. Verificar la moneda y si el precio incluye impuestos.
4. Confirmar la zona horaria del sello de lectura.
5. Levantar el puente o el PMS con el contrato y correr la suite:

```bash
cd copiloto && ./.venv/bin/python -m pytest tests/test_pms_contract.py -q
```

6. Probar el flujo completo contra el stack: `make e2e`.
7. Revisar en el panel que la lectura muestre fecha y hora, y que la etiqueta `simulada`
   desaparezca.

## Si el API del proveedor no coincide

Se escribe un puente, no un adaptador nuevo. El puente es un servicio pequeño que traduce:

- su endpoint de disponibilidad a `GET /api/v1/availability`;
- sus códigos de habitación a los `code` estables del hotel;
- su moneda a pesos;
- su formato de fecha a ISO 8601 con zona;
- su autenticación a la cabecera configurada.

El puente tiene su propio repositorio y su propio despliegue. Así cada integración nueva es un
servicio de una pantalla, no un cambio en el copiloto.

## Fase 1 sin PMS

Un hotel que todavía no quiere abrir su inventario usa `PMS_ADAPTER=none`. El copiloto responde las
preguntas frecuentes, muestra la ubicación, captura fechas y personas, y deriva a recepción. Es el
modo con el que se puede empezar a medir sin tocar el PMS del cliente.

## Cómo se prueba

`copiloto/tests/test_pms_contract.py` describe el contrato: lectura válida con su sello, parámetros
correctos, payload fuera de rango, timeout, error 500, conflicto de reserva, rutas y cabecera
configurables, y el modo sin PMS. Diez pruebas que cualquier implementación debe pasar.
