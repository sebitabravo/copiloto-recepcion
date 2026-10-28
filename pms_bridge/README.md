# Puente Beds24

Traduce la API v2 de Beds24 al contrato del copiloto. El copiloto no cambia: apunta `PMS_URL` a este
servicio y recibe el mismo formato que el PMS simulado.

## Por qué Beds24

Es el PMS que más se repite entre alojamientos independientes de 10 a 40 habitaciones en
Latinoamérica, tiene API pública sin acuerdo de partner y el propio hotel puede generar su token.
Eso permite un piloto sin depender de que un proveedor apruebe una integración.

## Puesta en marcha

**1. Generar el invite code.** En Beds24: *Settings → Account → Access → Invite Codes*. Marca los
scopes de lectura de inventario. El código expira en 24 horas.

**2. Canjearlo por un refresh token.**

```bash
curl -s 'https://api.beds24.com/v2/authentication/setup' \
  -H 'accept: application/json' -H 'code: TU_INVITE_CODE'
```

Devuelve `token`, `expiresIn` y `refreshToken`. Guarda el **refreshToken**: no expira mientras se use
al menos una vez cada 30 días.

**3. Mapear las habitaciones.** En Beds24, cada tipo de habitación tiene un `roomId` numérico. El
puente necesita un código estable por habitación:

```bash
BEDS24_ROOMS='[
  {"code":"doble_con_jacuzzi","roomId":101,"name":"Doble con Jacuzzi","max_adults":2,"max_children":1,"m2":32},
  {"code":"doble_vista_jardin","roomId":102,"name":"Doble Vista Jardín","max_adults":2,"max_children":1,"m2":28}
]'
```

Los `code` son los que usa el copiloto al reservar y los que aparecen en la traza. No los cambies
después de configurar el hotel.

**4. Variables**

| Variable | Obligatoria | Qué hace |
|---|---|---|
| `BEDS24_REFRESH_TOKEN` | sí | Obtiene los tokens de acceso; el puente los renueva solo |
| `BEDS24_ACCESS_TOKEN` | alternativa | Token de vida larga (solo lectura), si no quieres refresh |
| `BEDS24_ROOMS` | sí | Mapa de habitaciones (arriba) |
| `BEDS24_CLP_RATE` | si la moneda no es CLP | Multiplicador a pesos. Ej. 1 USD = 950 → `950` |
| `BEDS24_TZ` | no | Zona del sello de lectura. Por defecto `America/Santiago` |

**5. Levantarlo**

```bash
docker compose -f infra/docker-compose.yml --project-directory . --profile beds24 up -d beds24-bridge
# o en local, para desarrollo
make bridge
```

**5.1 Verificar antes de conectar el copiloto**

```bash
make beds24-check
```

Comprueba el canje del token, los permisos, la lectura del calendario para los próximos días y que la
respuesta del puente cumpla el contrato. No escribe nada en Beds24.

**6. Apuntar el copiloto**

```bash
PMS_URL=http://beds24-bridge:8300
PMS_ADAPTER=http
```

Con eso, `check_availability` del copiloto lee el inventario real del hotel.

## Qué hace y qué no

- **Lee** disponibilidad y precio por rango de fechas y las convierte en ofertas por habitación.
- **No escribe** reservas: `POST /api/v1/bookings` responde 501. La confirmación es humana, en Beds24.
  El copiloto ya está diseñado así; el puente solo lo respeta.

## Decisiones de traducción

| Beds24 | Contrato del copiloto | Regla |
|---|---|---|
| `numAvail` por día | `available_units` | El **mínimo** de las noches. Si una noche está en 0, la habitación no se ofrece |
| `price1` por noche | `nightly_price_clp` | **Promedio** de las noches, redondeado. El copiloto multiplica por noches, así el total queda correcto |
| Moneda de la propiedad | CLP | Se aplica `BEDS24_CLP_RATE` |
| Sin `date` o con fecha faltante | — | La habitación no se ofrece: nunca se completa un dato inventado |

## Límites conocidos

- **Tarifas variables:** si el hotel cobra distinto cada noche, la oferta muestra el promedio. El
  total es correcto; el detalle por noche no se expone.
- **Impuestos:** Beds24 puede devolver precio sin impuestos según configuración. Verifica con el hotel
  antes del piloto.
- **Créditos de API:** Beds24 limita por créditos cada 5 minutos. El copiloto consulta una vez por
  conversación, no en bucle; para un hotel de 20 habitaciones sobra margen.

## Pruebas

```bash
cd pms_bridge && uv run pytest -q
```

Doce pruebas: lectura del mapa de habitaciones, mínimo de cupos, promedio de precio, conversión de
moneda, renovación de token, error de Beds24, filtro por capacidad, rango inválido, y que el puente no
escriba reservas.
