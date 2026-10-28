# Stack abierto

Regla del proyecto: **el copiloto funciona completo sin licencias de pago y sin depender de servicios
de terceros**. Este documento lista cada pieza, su licencia y qué queda fuera de esa regla.

## Componentes

| Pieza | Licencia | Costo para el hotel |
|---|---|---|
| Copiloto, PMS simulado y puente | código propio del proyecto | — |
| FastAPI · uvicorn · httpx · pydantic | MIT / BSD | — |
| PostgreSQL | PostgreSQL License | — |
| Redis 7 | BSD-3 | — |
| Chatwoot Community Edition | MIT (la carpeta `enterprise/` está excluida) | — |
| nginx | BSD-2 | — |
| Docker Engine y Compose | Apache 2.0 | — |
| llama.cpp | MIT | — |
| Qwen 2.5 (modelo) | Apache 2.0 | — |
| Python | PSF | — |
| Tipografías de la landing | Instrument Serif e Inter, SIL OFL, servidas desde el propio sitio | — |

## Lo que queda fuera, y por qué

| Pieza | Por qué no es nuestra | Alternativa abierta |
|---|---|---|
| **PMS del hotel** | Es el sistema del cliente. Si usa Beds24 (propietario), el hotel ya lo paga; nosotros no. Si usa HotelDruid (AGPLv3), puede correr todo abierto | HotelDruid: AGPLv3, PHP + MySQL/PostgreSQL/SQLite, sin API REST — el puente tendría que leer su base de datos |
| **Runtime de contenedores** | Docker Desktop y OrbStack son propietarios. OrbStack es gratis para uso personal | Podman o Colima, ambos open source |
| **Proveedor de WhatsApp** | Conectar el número oficial exige un BSP (Meta Cloud API o similar) y tiene costo por conversación | El stack ya opera con Chatwoot por widget web sin costo; WhatsApp queda como costo del canal, no del producto |

## Cómo se sostiene la regla

Dos guardarraíles automáticos, no una promesa:

1. El modelo por defecto es **local** (`http://host.docker.internal:11434/v1`, Qwen 2.5). Un proveedor
   de pago solo existe si alguien lo configura en el entorno.
2. La landing **no** carga fuentes, scripts ni imágenes de ningún CDN: las tipografías están en
   `landing/fonts/` y servidas por nginx.

Ambas cosas están en `copiloto/tests/test_stack_abierto.py`. Si mañana alguien mete un CDN o vuelve a
poner una API de pago por defecto, el test falla.

## Costo real de operar

| Concepto | Supuesto mensual |
|---|---|
| Servidor del hotel (stack completo) | 45.000 CLP |
| Respaldos y almacenamiento | 5.000 CLP |
| Soporte (2 h a 15.000) | 30.000 CLP |
| Conectividad y energía atribuibles | 10.000 CLP |
| Mensajería del canal | según proveedor; cero si se usa el widget web |
| Consultas de IA | **0**: el modelo corre en el equipo del hotel |

Total sin mensajería: 90.000 CLP. Es la cifra que ya usa la Unidad 2.

## Qué implica para el cliente

- No hay cuota por consulta ni por habitación.
- Los datos de huéspedes no salen del hotel.
- Si el modelo local no está disponible, el copiloto sigue atendiendo con el flujo guiado.
- La salida es posible: los datos viven en PostgreSQL y SQLite dentro del hotel.
