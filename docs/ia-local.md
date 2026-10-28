# IA local del copiloto

El copiloto puede responder con un modelo que corre en tu equipo, sin API pagada.
El modelo se ejecuta **en el host**; el contenedor lo alcanza por red. Así la
inferencia no compite con la memoria que Docker tiene asignada al stack.

## Requisitos

- `llama.cpp` instalado (`brew install llama.cpp` en macOS).
- Unos 3 GB de disco para el modelo de 3B, unos 5 GB para el de 7B.
- El stack levantado con `make up`.

## Puesta en marcha

```bash
./scripts/local-model.sh
```

El script imprime las variables que deben quedar en `.env` y levanta el servidor
en el puerto 11434. En otra terminal:

```bash
make up
```

Con eso el copiloto deja de responder "sin IA" y usa el modelo local.

## Antes de presentar

```bash
make demo
```

Verifica landing, copiloto, PMS y Chatwoot; levanta el modelo si está apagado; confirma que la IA
está activa y hace una consulta de calentamiento para que la primera respuesta de la demo no
pague la carga del modelo en memoria. Sale con código 1 si algo falta.

## Variables

| Variable | Valor | Para qué |
|---|---|---|
| `AI_MODE` | `full` o `assisted` | `full` permite crear la reserva en el PMS simulado; `assisted` solo reúne datos y deriva |
| `LLM_BASE_URL` | `http://host.docker.internal:11434/v1` | Endpoint compatible con OpenAI visto desde el contenedor |
| `LLM_MODEL` | `qwen2.5-7b-instruct` | Nombre del alias con que se levantó el modelo |
| `LLM_API_KEY` | `local` | El servidor local no valida clave, pero el copiloto exige una no vacía para activar la IA |
| `LLM_TIMEOUT_S` | `120` | Un modelo local en CPU tarda más de los 25 s por defecto |

## Elegir tamaño de modelo

| Equipo | Modelo sugerido | Disco |
|---|---|---|
| Mac con Apple Silicon | `Qwen/Qwen2.5-7B-Instruct-GGUF:Q4_K_M` | ~4,7 GB |
| Equipo con 4 a 8 GB de RAM total | `Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M` | ~1,9 GB |

```bash
LLM_MODEL_HF=Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M \
LLM_MODEL_NAME=qwen2.5-3b-instruct ./scripts/local-model.sh
```

Si cambias de modelo, actualiza `LLM_MODEL` en `.env` con el mismo nombre que
pasaste en `LLM_MODEL_NAME`.

## Qué pasa si el modelo no está

El copiloto no se cae: si el modelo no responde, la conversación sigue con el
flujo guiado por reglas y la traza lo marca como `fallback`. Es intencional, para
que la demo nunca quede muda.

## Medir antes de elegir

```bash
MODEL_EVAL_MODEL=qwen2.5-3b-instruct python scripts/model_eval.py
```

Corre doce conversaciones contra el agente real y reporta selección de
herramientas, argumentos, reservas sin confirmación, fugas de prompt, datos
personales repetidos y latencia p50 y p95. Sale con código 1 si hay un fallo
bloqueante.

Para comparar dos modelos, guarda cada reporte:

```bash
MODEL_EVAL_MODEL=qwen2.5-7b-instruct python scripts/model_eval.py --json > eval-7b.json
MODEL_EVAL_MODEL=qwen2.5-3b-instruct python scripts/model_eval.py --json > eval-3b.json
```
