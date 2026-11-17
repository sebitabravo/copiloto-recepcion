## Learned User Preferences

- Write product copy, reports, and slides for this project in Spanish.
- Keep the prototype and every academic deliverable faithful to a real hotel reception workflow and to what the EVA1 and EVA2 reports actually promised. Do not describe features the running prototype does not have.
- The voice and phone demo must use Sebastián's cloned ElevenLabs voice, Sebastián Bravo tco.
- EVA3 informe and slides must match the real dark bronze demo, the required instruments, and prior reports. Leave user-test tables empty until a real session exists; do not invent participants, times, or completed iterations.

## Learned Workspace Facts

- Copiloto de Recepción is an INACAP INNOVA3 academic prototype for Hotel Bordeluz, published at https://copiloto-recepcion.vercel.app. It is not the hotel's live site. Guest data, prices, inventory, and the 20-room plan are simulated, and the evaluation chat is simulated WhatsApp.
- The assistant orients, shows location first, answers the 14 approved FAQs in `data/hotel.yaml`, reads dated PMS availability, and hands off. It must not confirm a booking. Reception (demo persona Sofía) confirms in the PMS. Voice never books, even when `AI_MODE=full`.
- `AI_MODE=off` is the guided flow with no model; `assisted` is the EVA2 design and converses then hands off; `full` may create a booking only in the simulated PMS. `make demo-local` is the official evaluation start without Docker, Chatwoot, or a model, at http://localhost:8080/demo (copiloto on 8100, pms_mock on 8200). Outside 08:00–22:00 America/Santiago, Simular en turno is required to show the 3-minute clock. Targets are FAQ under 10 seconds and a human commercial reply under 180 seconds.
- The published site is a static demo: approved rules first, then DeepSeek through `api/demo/chat.mjs` using `data/hotel.yaml`, with ElevenLabs speech through `api/demo/tts.mjs`. Without keys it falls back to the script and the browser voice. Chatwoot and the local model are lab-only. Pxsol has no public API; a real PMS needs hotel credentials.
- Hotel facts marked `pendiente_validar` in `data/hotel.yaml` (address kilometers, beach distance, Sunday restaurant, pets, real shift hours, 90-day retention) must be stated as unconfirmed. `docs/eva3/testeo/registro-sesion.md` is still an empty template.
