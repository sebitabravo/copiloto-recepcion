# Hotel Boutique Bordeluz PMS mock

Local, simulated Pxsol-like hotel PMS. Python **3.12**, FastAPI, SQLite,
PyYAML, and uv; no npm, CDN, or external frontend assets.

## Run

```sh
cd pms_mock
uv run pytest -q
STAFF_TOKEN='replace-with-a-local-secret' uv run uvicorn pms_mock.main:app --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/admin` for reception's Spanish interface. Enter the
staff token and explicitly review/confirm the reservation; loading the page or
query parameters NEVER creates a booking. The token stays in the form, not URL
parameters or browser storage. `/docs` provides the API schema.

## Environment

| Variable | Default | Behavior |
| --- | --- | --- |
| `HOTEL_DATA_PATH` | Repository `data/hotel.yaml` (package-relative `../data/hotel.yaml`) | Existing YAML `rooms` catalog; missing file/key, invalid fields, duplicate codes, or a catalog other than 12 types fail fast. Relative overrides resolve from the working directory. |
| `PMS_DB_PATH` | `./pms.sqlite` | Persistent SQLite file; its parent directory must exist. |
| `STAFF_TOKEN` | unset | Required for booking create/list; unset or empty fails closed with 401. |
| `COPILOTO_EVENTS_URL` | unset | Optional booking event destination; only configure a trusted local endpoint. |
| `SIMULATE_DOWN` | unset | When exactly `1`, availability returns 503; read on each request. |

The source catalog is never modified, and its capacities are preserved exactly,
including the unusual one-adult limit of `doble_terraza_vista_lago`.
Changing catalog codes/order after initial seeding requires a fresh database;
a mismatched existing inventory fails startup rather than silently reseeding it.

## Simulated inventory and prices

**All physical-room distribution and nightly prices below are SIMULATED**, not
verified operational inventory or published rates. Each of the 12 YAML types gets
one room; the first eight get one additional room, totaling **20** physical units.
The database stores individual seed rows with stable IDs 1–20. Prices are CLP per
night, computed deterministically as `65000 + 5000 * YAML index` (zero-based).
The availability envelope and booking responses contain `simulated: true`.

| Room type code | Simulated units | Simulated CLP/night |
| --- | ---: | ---: |
| single_doble_vista_jardin | 2 | 65000 |
| doble_terraza_vista_lago | 2 | 70000 |
| doble_vista_piscina | 2 | 75000 |
| doble_con_jacuzzi | 2 | 80000 |
| triple_vista_interior_estacionamiento | 2 | 85000 |
| triple_vista_parcial_lago | 2 | 90000 |
| triple_con_terraza_vista_al_lago | 2 | 95000 |
| cuadruple_terraza_vista_al_lago | 2 | 100000 |
| cuadruple_vista_interior_estacionamiento | 1 | 105000 |
| cuadruple_vista_parcial_lago | 1 | 110000 |
| triple_con_vista_estacionamiento_entrada | 1 | 115000 |
| doble_sin_vista | 1 | 120000 |

## API

- `GET /health` returns `{"status":"ok"}`.
- `GET /api/v1/availability?checkin=2026-11-01&checkout=2026-11-04&adults=2&children=0`
  returns `read_at` in America/Santiago, `source: "pms-mock"`, `simulated: true`,
  and fitting room types with positive availability and simulated CLP prices.
- `POST /api/v1/bookings`, with `X-Staff-Token`, requires `guest_name`, `checkin`,
  `checkout`, `room_code`, `adults`, and `children`; `conversation_id` is optional
  integer/null. Returns 201 with `booking_id` and the booking fields.
- `GET /api/v1/bookings`, with `X-Staff-Token`, returns a JSON array of bookings.
- `GET /admin` serves local HTML and vanilla JS. Query prefills: `guest`, `checkin`,
  `checkout`, `room_code`, `adults`, `children`, and `conversation_id`.

Dates use half-open intervals `[checkin, checkout)`: a checkout frees inventory on
that date. Adults must be at least 1 and children at least 0. Invalid dates,
reversed/equal intervals, invalid party sizes or unknown types return 422.
Sold-out stays return 409. Availability is the unit count minus the peak nightly
occupancy during the requested stay, not the sum of disjoint reservations.
Inventory is pooled by type; this mock does not assign a particular physical room
to a guest. `BEGIN IMMEDIATE` serializes inventory validation plus insertion,
preventing simultaneous booking requests from overbooking.

After commit, FastAPI runs optional event delivery in its background thread pool,
so webhook I/O never delays the HTTP response or rolls back the reservation. It
sends `{"kind":"booking_confirmed","conversation_id":null,"booking_id":1}`
(with actual IDs), using a bounded 2-second HTTP timeout, an initial attempt plus
**three retries**, and 50/100/200 ms backoffs. HTTP errors and transport failures
are isolated. Events are best-effort, not durable: process shutdown can lose a
pending event; retries can duplicate delivery, so receivers should deduplicate by
booking ID. TestClient waits for background tasks, enabling deterministic mocks.

The staff token is a shared local simulation credential, not identity verification
or a production authentication system. The API requires staff possession; only
reception's explicit admin submit represents human confirmation in this mock.
