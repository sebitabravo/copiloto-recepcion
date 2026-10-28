# Codex C6 — Public demo landing

## Status
PASS. Redesigned only `landing/index.html`; preserved the deployment-generated `config.js` integration and original Chatwoot SDK loader/settings. No `config.js` was created and no git commands were run.

## Changes
- Warm, polished light/dark hotel layout with academic disclaimer, hero, chat-opening action and reduced-motion-aware navigation.
- Three guided demo steps with copyable messages, future stay dates generated as today +120 days and three nights, clipboard fallback and accessible announcements.
- Four inline-SVG feature cards with accurate deterministic-flow, dated simulated-PMS and human-confirmation explanations.
- Hotel location, allowed Google Maps link, prototype-view cards and four native FAQ accordions.
- Semantic landmarks, skip link, visible focus, responsive grids, 16px side gutters, touch-friendly controls and safe DOM updates.
- Kept guest-data and simulated-price/availability disclaimers. SDK failures produce the requested inline stack-start guidance.

## Checks performed
Independent browser-free verification passed:
- HTML nesting, unique IDs, one h1, semantic landmarks and four details/summary accordions.
- Resource/link URL allowlist: no external services beyond the specified localhost links and Google Maps; widget SDK URL remains configuration-driven.
- No inline event-handler attributes or `innerHTML`.
- Inline JavaScript syntax using `node --check`.
- Mocked JavaScript runtime verified dynamic +120-day/+3-night dates across daylight-saving, year and leap boundaries.
- Mocked configuration/SDK injection and run arguments, chat readiness/open action and unavailable-SDK message.
- Mocked clipboard success, textarea fallback and failed-copy announcements.

An initial contrast check identified insufficient contrast for small accent-colored text. Corrected with a darker light-theme text token while retaining the requested decorative accent. Final checks:

```text
Accent text contrast on #f6f0e6: 5.57:1 PASS
Accent text contrast on #fffaf2: 6.08:1 PASS
Accent text contrast on #eee2cf: 4.94:1 PASS
Final inline JavaScript syntax and safe DOM source check: PASS
```

Primary-button contrast is 4.94:1; checked dark-theme text pairs are at least 6.35:1.

## Limitations
No browser rendering, live widget request or mobile-overflow measurement was performed. Responsive behavior was checked structurally, not claimed as visually tested. Engram tools were unavailable; no memory persistence is claimed.

## Files
- `landing/index.html` — redesigned landing.
- `reports/codex-c6.md` — this report.
