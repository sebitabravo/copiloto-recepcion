# Verificación de /demo

## Automática (desde la raíz del repositorio)

```sh
node --test scripts/*.mjs          # interfaz y versión estática, sin red
cd copiloto && uv run pytest -q    # incluye tests/test_demo_requests.py (recorrido EVA 3)
```

`scripts/test-demo-split.mjs` fija formatos, render del hilo (el huésped no ve notas internas, los enlaces son
cortos y seguros), separación de roles, foco visible, que ninguna clase de `/demo` choque con `demo.css` y que
la demo conserve la marca, el hotel y la paleta de la portada.
`scripts/test-static-demo.mjs` recorre el caso canónico contra el servidor simulado y comprueba que ninguna
petición `/api` sale a la red.

## Manual en navegador (5 minutos)

Con `make demo-local LIMPIO=1`:

1. `/demo?vista=huesped` en modo teléfono (390 px): atajos visibles en dos filas, campo usable, sin
   desplazamiento horizontal. Tocar un atajo no abre el teclado.
2. `/demo?vista=recepcion`: pide el nombre, la lista se actualiza sola (≈4 s) y el reloj de espera avanza.
3. Caso canónico del guion (`docs/guion-demo.md`): resumen, envío, tomar, inventario, respuesta y recarga.
4. Tab recorre atajos, campo y botones con foco visible; el hilo anuncia mensajes nuevos (región `log`).
5. Modo oscuro del sistema: contraste correcto en burbujas, badges y ficha.
