# Codex C7 — Interactive hotel AI demo

## Status
PASS. Implemented the frontend against `docs/demo-api.md`, without backend changes. Independent mock-server/headless-browser verification passed 40 checks.

## Files
- `landing/index.html` — semantic Spanish landing, phone chat, action timeline, guided scenarios, retained location/prototype views/FAQ and disclaimers.
- `landing/demo.css` — warm responsive light/dark themes, phone frame, event/booking cards, aurora/reveal/typing animations and reduced-motion overrides.
- `landing/demo.js` — status/chat/reset API integration, configurable backend URL, session handling, safe text rendering, quick replies, cancellable guided scenarios, retries, cooldowns and secondary Chatwoot loader.
- `reports/codex-c7.md` — this report.

No `config.js` was created or modified. No git commands were run. Authored changes are confined to `landing/` and `reports/`; temporary test infrastructure was outside the repository.

## Implemented behavior
The main chat talks directly to the public demo API, renders tool actions and simulated booking tickets, reports model/capabilities and usage, and handles guided-mode fallback. Requests omit credentials and Authorization headers and use a 40-second AbortController timeout. Session IDs are validated and stored with guarded sessionStorage access. Untrusted assistant/event data is rendered only through safe DOM APIs.

Guided scenarios send actual requests one at a time, with typing and pauses; booking examples use today +120 days and three nights. Reset clears the UI only after the server reset succeeds and generates a new session. HTTP/network errors remain retryable; 429 responses enforce the returned countdown. Chatwoot remains a secondary option with the preserved configuration/settings/SDK run contract.

## Testing
Read `docs/demo-api.md` before implementation. Used a throwaway Python mock API and a separate temporary static server, with CORS configured for the landing origin. Configuration was served dynamically in the test handler, not written to `landing/config.js`. Headless Chrome through Playwright exercised real HTTP requests to that mock. Temporary servers, browser profiles and harness files were cleaned up.

40 browser checks passed, covering:
- Model/autonomous status, disabled-AI banner, status failure and retry.
- Initial/API quick replies, Enter versus Shift+Enter, 400-character UI counter and latest-only assistant announcements.
- Untrusted reply text: no injected image/script execution.
- Tool success/failure, argument chips, duration, booking fields/CLP formatting, handoff, fallback and usage counters.
- Ordered five-message booking scenario with dynamic dates; human-handoff scenario and cancellation.
- 503/network failure recovery, retry without duplicate user bubbles and 429 countdown/send gating.
- Reset success/failure and new session IDs.
- SessionStorage-blocked and randomUUID-unavailable fallbacks.
- Scroll pinning at the bottom and preserving the position of users reading earlier messages.
- No horizontal overflow at 360px and 1280px in both light and dark themes.
- Reduced-motion suppression and secondary Chatwoot settings/loader/open behavior through a local SDK stub.
- No Authorization or Cookie headers on demo requests.

Zero JavaScript page errors or unexpected console errors. Three expected browser resource-error logs resulted from deliberately injected HTTP 503/429 responses.

Additional checks passed: JavaScript syntax with `node --check landing/demo.js`, HTML nesting/unique IDs/one h1, no inline event handlers, no `innerHTML`, preserved relative config loader and explicit credential omission. Screenshots were visually inspected.

## Screenshots
- `reports/codex-c7-360-light-overview.png` — mobile initial phone view (about 70 KB).
- `reports/codex-c7-1280-dark-overview.png` — desktop dark overview (about 112 KB).
- `reports/codex-c7-360-light.png` — mobile conversation/tool state (about 59 KB).
- `reports/codex-c7-1280-dark.png` — simulated booking-ticket state (about 102 KB).

## Limitations
The parallel real AI backend and live Chatwoot service were not contacted; API behavior and SDK integration were tested against mocks/stubs. The 40-second timeout was source-inspected, not deliberately exhausted. Engram tools were unavailable; no memory persistence is claimed.
