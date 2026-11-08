# IA local del copiloto

El copiloto responde con un modelo que corre en tu equipo, sin API pagada y sin costo por consulta.
La vía recomendada es Docker: el modelo corre en la GPU NVIDIA si Docker la ve y, si no, en CPU con el
mismo modelo y el mismo comportamiento.

## Puesta en marcha

```bash
./scripts/demo.sh ia      # detecta la GPU, levanta el modelo y reconecta el copiloto con IA
./scripts/demo.sh ia-off  # apaga el modelo; el copiloto sigue con el flujo guiado
```

`ia` prueba si Docker ve una GPU NVIDIA (`docker run --gpus all … --list-devices`). Con GPU usa
`infra/docker-compose.ia.yml`; sin GPU agrega `infra/docker-compose.ia-cpu.yml` encima. `LLM_GPU=0`
fuerza la variante CPU. La primera vez descarga ~2,5 GB dentro del volumen `llm_models`.

A mano:

```bash
# GPU
docker compose -f infra/docker-compose.yml -f infra/docker-compose.ia.yml --project-directory . up -d llm copiloto
# CPU
docker compose -f infra/docker-compose.yml -f infra/docker-compose.ia.yml -f infra/docker-compose.ia-cpu.yml \
  --project-directory . up -d llm copiloto
```

### Requisitos de la GPU

- NVIDIA con driver reciente. La imagen `server-cuda` usa CUDA 12.8, que es el mínimo para las
  RTX 50xx (Blackwell); con un driver viejo llama.cpp cae a CPU sin avisar, por eso `ia` verifica el
  dispositivo antes de elegir.
- Windows: Docker Desktop con WSL2 y soporte de GPU
  ([docs de Docker](https://docs.docker.com/desktop/features/gpu/)). Linux: NVIDIA Container Toolkit.
- Comprobación rápida: `docker run --rm --gpus all --entrypoint /app/llama-server
  ghcr.io/ggml-org/llama.cpp:server-cuda-b12169 --list-devices` debe listar `CUDA0`
  (en Git Bash, antepón `MSYS_NO_PATHCONV=1`).

## Elección del modelo

Modelo: **Qwen3-4B-Instruct-2507** en `Q4_K_M` (`unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M`), servido por
llama.cpp `b12169`.

Se compararon tres candidatos con `scripts/model_eval.py` (12 conversaciones contra el agente real,
modo `full`, tope de 12 s por turno) en una RTX 5060 de 8 GB:

| Modelo | Dónde | Casos | p50 | p95 | Observación |
|---|---|---|---|---|---|
| Qwen2.5-3B-Instruct `Q4_K_M` (anterior) | CPU, 8 hilos | 10/12 | 12,0 s | 12,0 s | casi todos los turnos chocan con el tope de 12 s; no llama la herramienta del hotel |
| Qwen3.5-4B `UD-Q4_K_XL` | GPU | 10/12 | 2,2 s | 9,0 s | su plantilla rechaza mensajes de sistema a mitad de la conversación (`System message must be at the beginning`) |
| **Qwen3-4B-Instruct-2507 `Q4_K_M`** | GPU | **11/12** | **1,5 s** | **5,7 s** | genera a ~65–100 tokens/s; el caso que falla es de prompt (resume en vez de pedir la propuesta al servidor) |

Por qué este modelo:

- **Llamado de herramientas**: la model card publica BFCL-v3 61,9 y TAU2-Retail 40,4, y en la
  evaluación local fue el único que acertó herramienta y argumentos en todos los casos de disponibilidad.
- **Sin razonamiento**: es la variante *Instruct* de Qwen3, sin bloques `<think>`; `--reasoning off`
  lo asegura y ninguna etiqueta de pensamiento llega al huésped.
- **Cabe con holgura en 8 GB**: ~2,5 GB de pesos más ~1,2 GB de caché para 8.192 tokens; el turno más
  largo de la evaluación usó ~4.000.
- **Latencia de chat**: p95 bajo los 5–6 s, en línea con la meta de la guía de agentes (texto p95 < 5 s).

No hay un benchmark público de español para estos tamaños: la decisión se apoyó en la evaluación local y en
lectura de las respuestas. Fuentes: [model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507),
[llama.cpp en Docker](https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md),
[servidor de llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md),
[GPU en Compose](https://docs.docker.com/compose/how-tos/gpu-support/).

### Banderas del servidor

| Bandera | Valor | Por qué |
|---|---|---|
| `-ngl` | `99` | todas las capas en la GPU (solo en `docker-compose.ia.yml`) |
| `-c` | `8192` | sobra para prompt, herramientas y 12 mensajes de historial |
| `--parallel` | `1` | una conversación a la vez en la demo; todo el caché para ella |
| `--jinja` | — | plantilla de chat del modelo, necesaria para las herramientas |
| `--reasoning` | `off` | sin bloques de razonamiento |
| `--cache-reuse` | `256` | reutiliza el prefijo común (prompt de sistema y herramientas) entre turnos |
| `--top-k` / `--top-p` / `--min-p` | `20` / `0.8` / `0` | muestreo recomendado por la model card |

La temperatura la envía el copiloto en cada petición (`LLM_TEMPERATURE`, ver [asistente con IA](ia.md)):
un valor bajo prioriza que repita los datos de las herramientas tal como vienen.

La imagen va con etiqueta fija (`server-cuda-b12169`, `server-b12169`): las etiquetas móviles cambian cada
noche y ya tuvieron regresiones. Para actualizar, cambia la etiqueta en los dos archivos y vuelve a evaluar.

## Variables

`docker-compose.ia.yml` las fija para el contenedor del copiloto; solo hacen falta en `.env` si el modelo
corre fuera de Docker.

| Variable | GPU | CPU | Para qué |
|---|---|---|---|
| `LLM_BASE_URL` | `http://llm:8080/v1` | igual | endpoint compatible con OpenAI visto desde el copiloto |
| `LLM_MODEL` | `qwen3-4b-instruct-2507` | igual | alias con que se levantó el modelo |
| `LLM_API_KEY` | `local` | igual | el servidor local no la valida, pero el copiloto exige una no vacía |
| `LLM_TIMEOUT_S` | `30` | `120` | tope de una llamada al modelo |
| `AI_TURN_TIMEOUT_S` | `25` | `90` | tope de un turno completo (varias llamadas y herramientas) |
| `AI_MODE` | `assisted` | igual | `assisted` reúne datos y deriva; `full` crea la reserva en el PMS simulado |

## Fuera de Docker

`./scripts/local-model.sh` levanta el mismo modelo con un `llama-server` instalado en el host (por ejemplo
`brew install llama.cpp` en macOS). Usa la GPU (Metal o CUDA) si la hay e imprime las variables para `.env`.

## Qué pasa si el modelo no está

El copiloto no se cae: si el modelo no responde, la conversación sigue con el flujo guiado por reglas y la
traza lo marca como `fallback`. Es intencional, para que la demo nunca quede muda.

## Medir antes de cambiar de modelo

```bash
MODEL_EVAL_MODEL=qwen3-4b-instruct-2507 uv run --project copiloto python scripts/model_eval.py
```

Corre las conversaciones de prueba contra el agente real y reporta selección de herramientas, argumentos,
reservas sin confirmación, fugas de prompt, datos personales repetidos, tono y latencia p50/p95. Sale con
código 1 si hay un fallo bloqueante. Para comparar, guarda cada reporte con `--json` y levanta el candidato
en otro puerto con `docker run --gpus all … -p 127.0.0.1:11435:8080`, apuntando
`MODEL_EVAL_BASE_URL=http://localhost:11435/v1`.
