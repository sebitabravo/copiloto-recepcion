# Copiloto Recepción — Design System (extracted)

Extracted verbatim from two separate CSS sources. **These are two distinct systems**, not one:

- **Landing** — `landing/demo.css` (public marketing site, includes a simulated WhatsApp phone demo)
- **Panel** — `copiloto/src/copiloto/static/theme.css` (reception panel + metrics; its header comment states it *replicates the landing tokens* so both feel like the same product, but the copies have drifted)

Values below are only what is actually declared in those files. No invented tokens. Both files define light values in `:root` and override them under `@media (prefers-color-scheme: dark)`.

Source shorthand in every table below: **landing** = `landing/demo.css`; **panel** = `copiloto/src/copiloto/static/theme.css`; **both** = those two exact paths. This is an extraction, not a proposed starter system.

Inventory (unique named properties, not counting dark overrides): landing **27 colors, 3 font stacks, 1 spacing token, 0 radius tokens, 3 shadows**; panel **15 colors, 2 font stacks, 0 spacing/radius tokens, 1 shadow, 1 easing token**. The board uses system-font fallbacks without loading the source webfonts. Board-only layout and swatch geometry are presentation, not additional product tokens.

---

## 1. Colors

### Shared page chrome — identical in both sources (light)

| Token | Value | Used for | Source |
| --- | --- | --- | --- |
| `--bg` | `#f3ebdf` | Page background | both `:root` |
| `--bg-2` | `#eae0cf` | Secondary background / ticker | both `:root` |
| `--card` | `#fcf8f1` | Card surfaces | both `:root` |
| `--card-2` | `#f6efe3` | Nested / muted card surfaces | both `:root` |
| `--ink` | `#211a12` | Primary text | both `:root` |
| `--ink-2` | `#423325` | Secondary text | both `:root` |
| `--line` | `#ded0b9` | Borders | both `:root` |
| `--accent` | `#8d5a2b` | Links, primary actions, brand (bronze) | both `:root` |
| `--accent-2` | `#35513f` | Secondary accent (green) | both `:root` |
| `--accent-ink` | `#fffaf2` | Text on accent | both `:root` |
| `--glow` | `#dfae7f` | Radial glows / stage light | both `:root` |

### Shared page chrome — identical dark values

| Token | Dark value | Source |
| --- | --- | --- |
| `--bg` | `#14100b` | both |
| `--bg-2` | `#1a1410` | both |
| `--card` | `#201a13` | both |
| `--card-2` | `#261e16` | both |
| `--ink` | `#f0e6d5` | both |
| `--ink-2` | `#d6c7b1` | both |
| `--line` | `#3f3427` | both |

### Landing-only tokens

| Token | Light | Dark | Used for | Source |
| --- | --- | --- | --- | --- |
| `--muted` | `#6b5943` | `#a4947d` | Muted text | `landing/demo.css` `:root` / dark block |
| `--line-soft` | `rgb(46 32 18 / 9%)` | `rgb(255 240 220 / 8%)` | Hairlines, hover fills, grid lines | `landing/demo.css` |
| `--accent-soft` | `#eaddc6` | `#33281c` | Rate-status strip background | `landing/demo.css` |
| `--bezel` | `#241a12` | `#2e2418` | Phone bezel / device sides | `landing/demo.css` |
| `--ok` | `#2c6340` | `#9bd2a3` | Success text, results and status dots | `landing/demo.css` |
| `--ok-bg` | `#e6eee2` | `#1e3125` | Success ticket and risk badge surfaces | `landing/demo.css` |
| `--error` | `#9c2a22` | `#ffc0b8` | Error text | `landing/demo.css` |
| `--error-bg` | `#fbeae4` | `#432723` | Error surfaces (`.notice.error`, `.chat-error`) | `landing/demo.css` |

**Landing WhatsApp demo tokens** (the simulated phone; named `--wa-*`):

| Token | Light | Dark | Used for | Source |
| --- | --- | --- | --- | --- |
| `--wa-bg` | `#efeae2` | `#0b141a` | Chat wallpaper | `landing/demo.css` |
| `--wa-in` | `#ffffff` | `#202c33` | Bot/assistant bubble background | `landing/demo.css` |
| `--wa-out` | `#d9fdd3` | `#005c4b` | Guest (user) bubble background | `landing/demo.css` |
| `--wa-header` | `#f0f2f5` | `#202c33` | Phone header / composer | `landing/demo.css` |
| `--wa-ink` | `#111b21` | `#e9edef` | Bubble text | `landing/demo.css` |
| `--wa-muted` | `#667781` | `#8696a0` | Timestamps, placeholders, status dot default | `landing/demo.css` |
| `--wa-line` | `#e2ddd4` | `#2a3942` | Header/composer borders, quick-reply borders | `landing/demo.css` |
| `--wa-link` | `#006b58` | `#7ee0c6` | Quick-reply button text | `landing/demo.css` |

**Landing hardcoded colors** (not tokens, declared inline):

| Value | Used for | Source |
| --- | --- | --- |
| `#00a884` | `.composer .send-button` background | `landing/demo.css` |
| `#019475` | Send button hover bg | `landing/demo.css` |
| `#25d366` | `.status-dot.ready` (+ `rgb(37 211 102 / 18%)` ring) | `landing/demo.css` |
| `#53bdeb` | Message tick marks | `landing/demo.css` |
| `#40230d` | Color-mix endpoint in `.brand-mark`, `.gh .av` and `.avatar` gradients | `landing/demo.css` |
| `#fff` | Send button text | `landing/demo.css` |

### Panel-only tokens

| Token | Light | Dark | Used for | Source |
| --- | --- | --- | --- | --- |
| `--muted` | `#7b6953` | `#a4947d` | Muted text | `copiloto/src/copiloto/static/theme.css` |
| `--ok` | `#2e7d32` | `#66bb6a` | Success status | `copiloto/.../theme.css` |
| `--warn` | `#b26a00` | `#ffb74d` | Warning status | `copiloto/.../theme.css` |
| `--bad` | `#c62828` | `#ef5350` | Failure status / `pulse-red` animation | `copiloto/.../theme.css` |

The panel has **no** `--line-soft`, `--accent-soft`, `--bezel`, `--ok-bg`, `--error*`, or any `--wa-*` tokens. Landing has **no** `--warn`/`--bad`.

### ⚠ Conflicts (same role, different value between the two systems)

| Role | Landing | Panel | Mode |
| --- | --- | --- | --- |
| Muted text (`--muted`) | `#6b5943` | `#7b6953` | light |
| Success (`--ok` vs `--ok`) | `#2c6340` (+ `--ok-bg #e6eee2`) | `#2e7d32` | light |
| Error (`--error` vs `--bad`) | `#9c2a22` | `#c62828` | light |
| Accent (`--accent`) | `#dcaa6d` | `#d1a971` | dark |
| Accent 2 (`--accent-2`) | `#9fd0ae` | `#8fb59c` | dark |
| Accent ink (`--accent-ink`) | `#14100b` | `#1d1812` | dark |
| Glow (`--glow`) | `#6a4a2a` | `#8d5a2b` | dark |
| Base font size / line height | `16px / 1.65` | `14px / 1.5` | both |
| Easing | `cubic-bezier(.2, .8, .3, 1)` | `--ease: cubic-bezier(.22, 1, .36, 1)` | both |
| Shadow scale | 3 tokens (`sm/md/lg`) | 1 token (`--shadow`) | both |
| Inter weight range (`@font-face`) | `400 700` | `100 900` | both |

Webfont loading is now identical: all three `@font-face` rules in each source use `font-display: swap`.

The panel also renames roles: landing `--error`/`--error-bg` vs panel `--bad`/`--warn` (no bg variants).

---

## 2. Typography

### Families

| Role | Stack | Source |
| --- | --- | --- |
| Display (serif) | `"Instrument Serif", "Iowan Old Style", "Palatino Linotype", Georgia, serif` | both `:root` (`--font-display`); `@font-face` for Instrument Serif 400 normal + italic in both |
| UI (sans) | `Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif` | landing `--font-ui` |
| UI (sans) | `"Inter", system-ui, -apple-system, "Segoe UI", sans-serif` | panel `--font-body` (no `ui-sans-serif` step) |
| Mono | `ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace` | landing `--font-mono` (panel declares **no** mono stack) |
| `@font-face` Inter weight range | `400 700` (landing) / `100 900` (panel); both `font-display: swap` | both |

### Weights actually used

Landing (`landing/demo.css`):
- `400` — h1, h2, `.booking-ticket .ticket-total`, `.booking-proposal .ticket-total`; Instrument Serif faces
- `500` — `.brand-tag`, `.float`, `.ghost-trace b`
- `600` — h3, `.button`, `.nav-cta`, `.pill`, `.phone-contact strong`, `.availability-head`, `.chip`, `.secondary-chat .text-button`, console controls
- `650` — `.brand`, `.eyebrow`
- `700` — `.event-result`, `.float.tool b`, `.float.ticket em`

Panel (`copiloto/src/copiloto/static/theme.css`): h1/h2 and Instrument Serif faces explicitly use `400`; Inter declares the `100 900` face range, not a component weight scale.

### Sizes (landing)

| Element | Size | Line height | Source |
| --- | --- | --- | --- |
| body | `16px` | `1.65` | `landing/demo.css` `body` |
| h1 | `clamp(2.7rem, 5.6vw, 4.5rem)` (mobile `clamp(2.4rem, 10vw, 3.2rem)`) | `.99` | `landing/demo.css` |
| h2 | `clamp(1.85rem, 3.4vw, 2.8rem)` | `1.05` | `landing/demo.css` |
| h3 | `1rem` | `1.35` | `landing/demo.css` |
| `.lede` | `1.06rem` | `1.62` | `landing/demo.css` |
| `.stat dt` | `1.9rem` (`1.6rem` ≤620px) | `1.1` | `landing/demo.css` |
| `.step .num` | `1.5rem` | `1` | `landing/demo.css` |
| `.booking-ticket .ticket-total` | `1.35rem` | — | `landing/demo.css` |
| Component text examples | eyebrow `.71rem`, pill `.72rem`, message `.85rem/1.6`, small `.82rem`, section-intro `.96rem` | — | `landing/demo.css` |

### Sizes (panel)

| Element | Size | Line height | Source |
| --- | --- | --- | --- |
| body | `14px` | `1.5` | `copiloto/.../theme.css` `body` |
| h1, h2 | no size declared (family + weight 400 + `letter-spacing: -.01em` only) | — | `copiloto/.../theme.css` |

Letter spacing (`landing/demo.css` unless marked panel): h1 `-.02em`, h2 `-.015em`, h3 `-.005em`, brand `-.01em`, panel h1/h2 `-.01em`; eyebrow `.19em`, turn-label `.12em`, stamp `.12em`, chat-date `.08em` (the last four uppercase).

---

## 3. Spacing

No general spacing scale or `--space-*` tokens exist. Landing now declares **one spacing token**, `--section-space: clamp(60px, 8vw, 88px)` in `landing/demo.css` `:root`.

- Landing `main > section`: `padding-block: var(--section-space)`; `main > #probar` sets `padding-top: 0`. The ≤620px `section { padding: 52px 0 }` declaration does not override the more specific direct-child rule.
- Landing `.wrap`: max-width `1180px`, padding-inline `24px` (`18px` ≤620px).
- Landing `.hero`: gap `56px`, padding-block `64px 56px`; ≤1000px one column, gap `34px`, padding-block `34px 54px`.
- Landing `.card`: padding `26px` (`20px` ≤620px); `.live-card`: `24px 22px`; `.shot`: `18px`.
- Landing `.button`: padding `12px 24px` (inline `18px` ≤620px), min-height `50px`; `.pill`: `6px 12px`.
- Landing touch targets: min-height `44px` on buttons, nav links, quick replies, textarea, send button, demo switch and console tabs.
- Landing `.tab-panel`: padding-block `44px 64px` (`24px 40px` ≤620px); adjacent child sections use margin-top and padding-top `34px`.
- Panel (`copiloto/src/copiloto/static/theme.css`): no spacing tokens or component padding/gap rules; `body { margin: 0 }`.

---

## 4. Radii

**No radius scale tokens.** Raw values:

### Landing (`landing/demo.css`)

| Radius | Applied to |
| --- | --- |
| `999px` | `.button`, nav links, `.pill`, `.chip`, `.float`, quick replies, `.event-source`, `.voice-typed input`, `.voice-lang select`, `.live-button`, notice buttons, `.demo-switch`, `.console-tabs` and tabs |
| `50%` | `.status-dot`, `.live-dot`, `.avatar`, send button, typing dots, `.sd`, `.dot`, `.avail`, switch knob |
| `40px` | `.phone` (`18px` ≤620px) |
| `26px` | `.frame`, `.cta` |
| `24px` | `.demo-stage` ≤820px (`0` ≤620px); no base radius declared in this source |
| `22px` (18px ≤620px) | `.card`; `.pipeline` stays `22px` |
| `18px` | `.shot`, `.list`, `.live-card`, `.admin-frame` |
| `14px` | `.event-card`, `.float.ticket` |
| `12px` | `.notice`, `.voice-line`, `.booking-proposal`, `.console-state`, `.console-notes li` |
| `11px` | `.ghost-trace li` |
| `10px` | `.skip`, `.availability`, `.brand-mark`, `.console-row` |
| `8px` | `.event-icon`, disclaimer right corners |
| `7px` | `.chat-date` |
| `6px` | `.arguments span`, `.tag` |
| `5px` | `.booking-ticket .stamp` |
| `22px` | composer `textarea` |
| Bubbles (main demo) | `.bubble` bot `10px 10px 10px 2px`, user `10px 10px 2px 10px` |

### Panel (`copiloto/.../theme.css`)

- `.skeleton`: `border-radius: 8px` — the only radius in the file.

---

## 5. Shadows

### Landing — 3 tokens

| Token | Light | Dark | Source |
| --- | --- | --- | --- |
| `--shadow-sm` | `0 1px 2px rgb(50 33 16 / 6%), 0 6px 18px rgb(50 33 16 / 5%)` | `0 1px 2px rgb(0 0 0 / 30%)` | `landing/demo.css` |
| `--shadow-md` | `0 2px 6px rgb(50 33 16 / 6%), 0 18px 42px rgb(50 33 16 / 9%)` | `0 2px 6px rgb(0 0 0 / 30%), 0 18px 42px rgb(0 0 0 / 40%)` | `landing/demo.css` |
| `--shadow-lg` | `0 40px 90px -30px rgb(50 33 16 / 34%)` | `0 40px 90px -30px rgb(0 0 0 / 70%)` | `landing/demo.css` |

Inline micro-shadows (not tokens): `0 1px 1px rgb(11 20 26 / 13%)` on `.bubble`, `.msg`, `.typing`; `0 1px 1px rgb(11 20 26 / 10%)` on `.chat-date`; `0 1px 1px rgb(11 20 26 / 8%)` on `textarea` and quick replies.

### Panel — 1 token

| Token | Light | Dark | Source |
| --- | --- | --- | --- |
| `--shadow` | `0 1px 2px rgb(46 32 18 / 6%), 0 10px 24px -18px rgb(46 32 18 / 45%)` | `0 1px 2px rgb(0 0 0 / 35%), 0 14px 30px -22px rgb(0 0 0 / 80%)` | `copiloto/.../theme.css` |

Landing inline effects (`landing/demo.css`): primary button `0 10px 26px -12px var(--accent)` plus `inset 0 1px 0 rgb(255 255 255 / 28%)`; phone `inset 0 0 0 1px rgb(255 255 255 / 8%), 0 0 0 1px rgb(30 20 10 / 14%), 0 30px 70px -32px rgb(40 26 12 / 55%)`; live status rings `0 0 0 3px color-mix(in oklab, var(--ok) 20%, transparent)` (or `--error`).

---

## 6. Borders

All component border rules here come from `landing/demo.css`; panel `theme.css` declares no component borders.

- Standard hairline: `1px solid var(--line)` on cards, buttons, pills, event cards and pipeline.
- Dashed variants: `.ghost-trace li`, `.event-source`, `.chip`, `.artifact`, `.console-state`, `.secondary-chat` top border use `var(--line)`; `.booking-ticket .stamp` uses `var(--ok)`.
- Accent borders: `.disclaimer` / `.float.ticket` left border `3px solid` (`--accent` / `--ok`); `.booking-proposal` `2px solid var(--accent)`; `.console-state.gate` border-color `color-mix(in oklab, var(--accent) 40%, var(--line))`.
- `.phone`: `8px solid var(--bezel)`; ≤620px `1px solid var(--line)`.
- Focus on links, buttons, textarea and `[tabindex]`: `3px solid var(--accent)`, offset `3px`; no radius declared. `main[tabindex="-1"]:focus` and `.tab-panel:focus` suppress their outline.

---

## 7. Motion / easing

### Landing
- Signature easing: `cubic-bezier(.2, .8, .3, 1)` (not tokenized) on transitions `.25s–.7s` and `message-in .28s`
- Keyframes: `aurora` 18s, `ticker` 40s linear, `message-in` .28s (`.event-card` .32s), `typing` 1s, `stack-float` 12s; reveal transitions .5–.6s with `.08/.16/.24s` stagger delays
- `.is-offscreen`, its descendants and `body.is-hidden *` pause animations; reduced motion also neutralizes the `.frame` transform.
- `prefers-reduced-motion: reduce` → `animation: none !important; transition: none !important` globally, `scroll-behavior: auto`, reveal states neutralized.

### Panel
- Tokenized easing: `--ease: cubic-bezier(.22, 1, .36, 1)`
- Keyframes: `rise` .42s, `pop` .5s (staggered via `--i` * 60ms), `pulse-red`, `shimmer` 1.4s linear
- `prefers-reduced-motion: reduce` → all durations `.001ms`, iteration 1, `scroll-behavior: auto`.

---

## 8. Component rules

### Landing

**Button** (`.button`, `landing/demo.css`)
- Base: inline-flex, gap 10px, min-height 50px, padding `12px 24px`, radius `999px`, border `1px solid var(--line)`, bg `var(--card)`, color `var(--ink)`, font `.92rem`/600
- Primary: transparent border, bg `linear-gradient(160deg, color-mix(in oklab, var(--accent) 88%, #fff), var(--accent))`, color `var(--accent-ink)`, inset white top highlight + `0 10px 26px -12px var(--accent)` glow
- Ghost: transparent bg
- Hover: `translateY(-2px)` + `--shadow-md`; primary hover deepens glow; disabled: `opacity: .5`, `cursor: not-allowed`

**Card** (`.card`)
- Padding 26px, border `1px solid var(--line)`, radius 22px, bg `var(--card)`, `--shadow-sm`
- `.shot` and `.live-card` use `linear-gradient(180deg, var(--card), var(--card-2))`, radius `18px`. `.shot` has padding `18px`, `--shadow-sm` and hover lift `translateY(-4px)`; `.live-card` has padding `24px 22px`, with no card-level hover lift declared.

**WhatsApp message bubbles** (`.message` / `.bubble`)
- `.messages`: column flex, gap `8px`, padding `14px 10px`, height `clamp(420px, 64vh, 580px)` (`min(68vh, 520px)` ≤620px). `.phone` supplies `--wa-bg` with a 1px dot pattern (`radial-gradient(circle at 1px 1px, rgb(0 0 0 / 4%) 1px, transparent 0)`) tiled at `18px 18px`.
- Bot (assistant): `align-self: flex-start`, radius `10px 10px 10px 2px`, bg `--wa-in`, color `--wa-ink`, shadow `0 1px 1px rgb(11 20 26 / 13%)`
- Guest (user): `align-self: flex-end`, radius `10px 10px 2px 10px`, bg `--wa-out`
- Text: `.85rem / 1.6`, `overflow-wrap: anywhere`; timestamp `.59rem`, `--wa-muted` (user override `color-mix(in oklab, var(--wa-ink) 55%, transparent)`), tabular-nums, right-aligned
- Entry animation: `message-in .28s cubic-bezier(.2,.8,.3,1)`
- Hero preview `.msg`: padding `8px 11px`, the same `10px` corner patterns, font `.78rem/1.5`; `.msg time` `.58rem`. Its `.frame .guest` wallpaper tile is `17px 17px`.

**Status dot** (`.status-dot`, `.live-dot`)
- Default: `7px` circle, bg `--wa-muted`
- Ready: bg `#25d366` + `0 0 0 3px rgb(37 211 102 / 18%)` ring
- Live card variant `.live-dot`: `9px`, `--line` default; `.is-ok` → `--ok` + ring `color-mix(--ok 20%)`; `.is-error` → `--error` + ring

**Badges / labels** (landing)
- `.pill`: padding `6px 12px`, radius `999px`, border `1px solid var(--line)`, bg `--card`, color `--accent`, `.72rem`/600
- `.arguments span`: mono chip, padding `3px 7px`, radius 6px, border `1px solid var(--line)`, color `--muted`, `.63rem`
- `.event-source`: dashed border pill, padding `3px 9px`, `--muted`, `.62rem`
- `.chip`: mono `.62rem`/600, padding `3px 9px`, border `1px dashed var(--line)`, radius `999px`, letter-spacing `.08em`, uppercase
- `.float`: mono `.66rem`/500, padding `7px 12px`, radius `999px`, background `color-mix(in oklab, var(--card) 88%, transparent)`, `backdrop-filter: blur(8px)`, `--shadow-sm`

**Panel rows / table rows** (landing availability list)
- `.availability-list li`: grid `minmax(0,1fr) auto`, gap `2px 12px`, `padding-top: 8px`, `border-top: 1px solid var(--line-soft)` between rows (none on first); label `.76rem`, strong `--ink`, meta `--muted`, total `--ink`/600 right-aligned
- `.pipeline`: five equal columns, radius `22px`, border `1px solid var(--line)`, `--shadow-sm`. `.step`: column flex, gap `8px`, padding `22px 20px`, left separator `1px solid var(--line-soft)` except first. ≤1000px the pipeline becomes one column and separators move to the top.
- `.voice-line`: padding `10px 14px`, radius 12px, bg `--card-2`; `.guest` variant `color-mix(--accent 10%, --card-2)`

**Other landing states**
- Error: `.notice.error`/`.chat-error` — bg `--error-bg`, color `--error`, retry button outlined `currentColor` pill
- Success ticket: `.booking-ticket` — bg `--ok-bg`, border `color-mix(--ok 40%, --line)`, heading `--ok`
- Focus: supported `:focus-visible` selectors → `outline: 3px solid var(--accent); outline-offset: 3px` (no radius).

**Demo console controls and states** (`landing/demo.css`)
- `.demo-switch`: min-height `44px`, padding `0 12px`, pill radius, `--card` surface, `--muted` text, `.84rem`/600. Track `30px × 18px`, knob `14px`, checked track `--accent-2` and knob `translateX(12px)`; disabled opacity `.55`.
- `.demo-banner`: background `color-mix(in oklab, var(--accent) 8%, var(--card))`, `--ink-2`, `.78rem`; `.is-off` uses `--card-2` / `--muted`.
- `.console-tabs`: max-width `520px`, gap `4px`, padding `5px`, pill radius, `--card`, `--shadow-sm`. Tabs: min-height `44px`, padding `10px 12px`, `.88rem`/600, `--muted`; selected `--ink` background / `--bg` text.
- `.console-row`: grid `minmax(0, 1fr) auto`, gap `2px 12px`, padding `10px 8px`, radius `10px`; hover `--line-soft`. Name `.84rem`; subtitle `.7rem` / `--muted`.
- `.console-state`: flex wrap, gap `6px 16px`, padding `14px 16px` (`12px` ≤480px), dashed `1px var(--line)` border, radius `12px`, `--card-2` / `--muted`, `.86rem`. Error uses `--error-bg` / `--error` and border-color `color-mix(in oklab, var(--error) 35%, var(--line))`; rate uses solid `--line`, `--accent-soft` / `--accent`; gate uses the same surface/text with border-color `color-mix(in oklab, var(--accent) 40%, var(--line))`.
- `.detail-list`: grid `auto minmax(0, 1fr)`, gap `6px 16px`, `.84rem`; ≤480px one column, gap `2px 0`.
- `.console-notes li`: padding `10px 12px`, `1px solid var(--line)`, radius `12px`, `--card-2` / `--ink-2`, `.8rem`; small text `.66rem` / `--muted`.
- `.admin-frame`: width `100%`, min-height `320px`, height `min(70vh, 720px)` (`60vh` ≤480px), border `1px solid var(--line)`, radius `18px`, `--card`.

### Panel

**Skeleton loader** (`.skeleton`, `copiloto/.../theme.css`)
- Radius 8px, `linear-gradient(90deg, var(--card-2) 25%, var(--card) 37%, var(--card-2) 63%)`, background-size 200%, `shimmer 1.4s linear infinite`

**Entrance animations**: `.rise` / `.pop` — `.42s`/`.5s var(--ease) both`, stagger `calc(var(--i, 0) * 60ms)`

The panel stylesheet defines **no** buttons, cards, rows, or tables — those components live in the panel templates, outside these two sources, and are therefore not recorded here.

---

## 9. What is NOT defined in the sources

- **General spacing scale** — landing has only `--section-space`; no `--space-*` scale in either file
- **Radius scale** — no tokens
- **Panel component rules** (buttons, cards, rows) — not in `theme.css`
- **Panel mono font stack** — not declared
- **Panel heading sizes** — family/weight only, no size
- **Panel component spacing/type scale** — no component padding/gaps or text sizes; body is `14px/1.5` and h1/h2 family/weight/tracking are declared

---

## Excepción declarada: piel de WhatsApp del simulador

El simulador de `/demo` imita a WhatsApp a propósito, así que usa los colores de marca de esa aplicación
en las burbujas y el botón de envío: `#00a884` (envío), `#019475` (hover de envío), `#25d366`
(estado listo), `#53bdeb` (marcas de leído) y `--wa-out: #d9fdd3` (burbuja saliente clara).
Fuente: `landing/demo.css`. La cabecera usa `--wa-header: #f0f2f5` en claro / `#202c33` en oscuro.

Los valores literales del canal no son tokens de marca del producto; los `--wa-*` sí están declarados
como tokens, pero solo en la landing. No deben extenderse al panel ni al resto de la portada: existen
para que el huésped reconozca el canal simulado. Cualquier otro componente sigue usando su sistema.
