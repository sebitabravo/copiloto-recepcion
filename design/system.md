# Copiloto Recepción — Design System (extracted)

Extracted verbatim from two separate CSS sources. **These are two distinct systems**, not one:

- **Landing** — `landing/demo.css` (public marketing site, includes a simulated WhatsApp phone demo)
- **Panel** — `copiloto/src/copiloto/static/theme.css` (reception panel + metrics; its header comment states it *replicates the landing tokens* so both feel like the same product, but the copies have drifted)

Values below are only what is actually declared in those files. No invented tokens. Both files define light values in `:root` and override them under `@media (prefers-color-scheme: dark)`.

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
| `--bezel` | `#241a12` | `#2e2418` | Phone bezel / 3D device frames | `landing/demo.css` |
| `--error` | `#9c2a22` | `#ffc0b8` | Error text | `landing/demo.css` |
| `--error-bg` | `#fbeae4` | `#432723` | Error surfaces (`.notice.error`, `.chat-error`) | `landing/demo.css` |

**Landing WhatsApp demo tokens** (the simulated phone; named `--wa-*`):

| Token | Light | Dark | Used for | Source |
| --- | --- | --- | --- | --- |
| `--wa-bg` | `#efeae2` | `#0b141a` | Chat wallpaper | `landing/demo.css` |
| `--wa-in` | `#ffffff` | `#202c33` | Bot/assistant bubble background | `landing/demo.css` |
| `--wa-out` | `#d9fdd3` | `#005c4b` | Guest (user) bubble background | `landing/demo.css` |
| `--wa-header` | `#f0f2f5` | `#202c33` | Phone header / composer / status bar | `landing/demo.css` |
| `--wa-ink` | `#111b21` | `#e9edef` | Bubble text | `landing/demo.css` |
| `--wa-muted` | `#667781` | `#8696a0` | Timestamps, placeholders, status dot default | `landing/demo.css` |
| `--wa-line` | `#e2ddd4` | `#2a3942` | Header/composer borders, quick-reply borders | `landing/demo.css` |
| `--wa-link` | `#006b58` | `#7ee0c6` | Quick-reply button text | `landing/demo.css` |

**Landing hardcoded colors** (not tokens, declared inline):

| Value | Used for | Source |
| --- | --- | --- |
| `#00a884` | WhatsApp send button bg, `.hc-tool b` accent | `landing/demo.css` |
| `#019475` | Send button hover bg | `landing/demo.css` |
| `#25d366` | `.status-dot.ready` (+ `rgb(37 211 102 / 18%)` ring) | `landing/demo.css` |
| `#53bdeb` | Message tick marks | `landing/demo.css` |
| `#40230d` | Color-mix endpoint in brand-mark/avatar/button gradients | `landing/demo.css` |
| `#0a0806` | Device camera bar | `landing/demo.css` |
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
| Webfont loading | `font-display: optional` | `font-display: swap` | both |

The panel also renames roles: landing `--error`/`--error-bg` vs panel `--bad`/`--warn` (no bg variants).

---

## 2. Typography

### Families

| Role | Stack | Source |
| --- | --- | --- |
| Display (serif) | `"Instrument Serif", "Iowan Old Style", "Palatino Linotype", Georgia, serif` | both `:root` (`--font-display`); `@font-face` for Instrument Serif 400 normal + italic in both |
| UI (sans) | `Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif` | landing `--font-ui` |
| UI (sans) | `Inter, system-ui, -apple-system, "Segoe UI", sans-serif` | panel `--font-body` (no `ui-sans-serif` step) |
| Mono | `ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace` | landing `--font-mono` (panel declares **no** mono stack) |
| `@font-face` Inter weight range | `400 700`, `font-display: optional` (landing) / `100 900`, `font-display: swap` (panel) | both |

### Weights actually used

- `400` — h1, h2, display numerals (`.metrics dt`, `.step .num`, `.booking-ticket .ticket-total`), body
- `500` — `.brand-tag`, `.ghost-trace b`
- `600` — h3, `.button`, `.brand`, nav-cta, `.pill`, `.phone-contact strong`, `.availability-head`, `.chip em`
- `650` — `.brand`, `.eyebrow`
- `700` — `.event-result`, `.ticket-float em`, `.secondary-chat .text-button`

### Sizes (landing)

| Element | Size | Line height | Source |
| --- | --- | --- | --- |
| body | `16px` | `1.65` | `landing/demo.css` `body` |
| h1 | `clamp(2.7rem, 5.6vw, 4.5rem)` (mobile `clamp(2.4rem, 10vw, 3.2rem)`) | `.99` | `landing/demo.css` |
| h2 | `clamp(1.85rem, 3.4vw, 2.8rem)` | `1.05` | `landing/demo.css` |
| h2 in `.thinking-heading` | `1.5rem` | — | `landing/demo.css` |
| h3 | `1rem` | `1.35` | `landing/demo.css` |
| `.subtitle` | `1.06rem` | `1.62` | `landing/demo.css` |
| `.metrics dt` | `1.5rem` | `1.1` | `landing/demo.css` |
| `.step .num` | `1.7rem` | `1` | `landing/demo.css` |
| `.booking-ticket .ticket-total` | `1.35rem` | — | `landing/demo.css` |
| Component text | `.58–.96rem` (e.g. eyebrow `.71rem`, pill `.72rem`, bubble `.85rem/1.6`, small `.82rem`, section-intro `.96rem`) | — | `landing/demo.css` |

### Sizes (panel)

| Element | Size | Line height | Source |
| --- | --- | --- | --- |
| body | `14px` | `1.5` | `copiloto/.../theme.css` `body` |
| h1, h2 | no size declared (family + weight 400 + `letter-spacing: -.01em` only) | — | `copiloto/.../theme.css` |

Letter spacing: h1 `-.02em`, h2 `-.015em`, h3 `-.005em`, brand `-.01em`, panel h1/h2 `-.01em`; eyebrow `+.19em`, turn-label `+.12em`, stamp/chat-date `+.08–.12em` (uppercase).

---

## 3. Spacing

**No spacing scale is declared in either source** — no `--space-*` tokens exist. All spacing is raw values. The recurring landing values:

- Page: `.wrap` max-width `1180px`, padding-inline `24px` (18px ≤620px); sections `padding: 76px 0` (52px mobile)
- Cards: `.card` padding `26px` (20px mobile); `.capability`/`.live-card` padding `24px 22px`
- Buttons: `.button` `padding: 12px 24px`, min-height `50px`; pill/label `padding: 6px 12px`
- Touch targets: `min-height: 44px` enforced on nav links, buttons, quick replies, textarea, send button
- Gaps used: `2, 4, 5, 6, 7, 8, 10, 12, 14, 16, 18, 20, 22, 24, 34, 40, 56px`; hero gap `56px`, demo-grid gap `34px`
- Panel: no spacing values at all beyond `body { margin: 0 }` and the skeleton radius.

---

## 4. Radii

**No radius scale tokens.** Raw values:

### Landing (`landing/demo.css`)

| Radius | Applied to |
| --- | --- |
| `999px` | `.button`, nav links, `.pill`, `.chip`, quick replies, `.hero-composer`, textarea-adjacent composer, `.event-source`, `.voice-typed input`, `.voice-lang select`, `.live-button`, notice buttons |
| `50%` | `.status-dot`, `.live-dot`, `.avatar`, send button, typing dots, orbit dot |
| `34px` / `40px` | `.hero-phone` / `.phone` |
| `30px` (24px mobile) | `.demo-stage` |
| `22px` (18px mobile) | `.card` |
| `18px` | `.capability`, `.live-card`, `.hero-chat`, `.plate`, phone ≤620px |
| `16px` | `.ticket-float` |
| `14px` | `.event-card` |
| `12px` | `.notice`, `.scenario-buttons button`, `.voice-line`, `.booking-proposal` |
| `11px` | `.ghost-trace li` |
| `10px` | `.skip`, `.availability` |
| `9px` | `.hc` bubbles: bot `9px 9px 9px 2px`, user `9px 9px 2px 9px` |
| `8px` | `.event-icon`, disclaimer right corners |
| `7px` | `.chat-date` |
| `6px` | `.hc-tool`, `.arguments span`, `.capability code` |
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

Plus a repeated **bubble micro-shadow** inline (not tokenized): `0 1px 1px rgb(11 20 26 / 8–13%)` on `.bubble`, `.hc`, `.chat-date`, `textarea`, quick replies.

### Panel — 1 token

| Token | Light | Dark | Source |
| --- | --- | --- | --- |
| `--shadow` | `0 1px 2px rgb(46 32 18 / 6%), 0 10px 24px -18px rgb(46 32 18 / 45%)` | `0 1px 2px rgb(0 0 0 / 35%), 0 14px 30px -22px rgb(0 0 0 / 80%)` | `copiloto/.../theme.css` |

Glow accents (landing, inline): `0 10px 26px -12px var(--accent)` on primary button; `0 0 72px -16px` accent glow on phone; status rings `0 0 0 3px color-mix(... 18–20%, transparent)`.

---

## 6. Borders

- Standard hairline: `1px solid var(--line)` (cards, buttons, pills, event cards, steps, sections) — both systems.
- Landing dashed variants: `.ghost-trace li`, `.event-source`, `.booking-ticket .stamp`, `.stage-orbit`, `.secondary-chat` top border — `1px dashed var(--line)` or `var(--ok)`.
- Landing accent borders: `.disclaimer` / `.ticket-float` left border `3px solid` (`--accent` / `--ok`); `.booking-proposal` `2px solid var(--accent)`; hover border `color-mix(in oklab, var(--accent) 40%, var(--line))`.
- Landing device border: `.phone` `8px solid var(--bezel)`; focus outline `3px solid var(--accent)`, offset 3px, radius 4px.

---

## 7. Motion / easing

### Landing
- Signature easing: `cubic-bezier(.2, .8, .3, 1)` (not tokenized) on transitions `.2s–.7s` and `message-in .28s`
- Keyframes: `aurora` 18s, `ticker` 40s linear, `message-in` .28s, `typing` 1s, `stack-float` 12s; reveal transitions .5–.6s with `.08/.16/.24s` stagger delays
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
- Gradient siblings: `.capability`, `.live-card` use `linear-gradient(180deg, var(--card), var(--card-2))`, radius 18px, hover lift `translateY(-4px)` + accent border

**WhatsApp message bubbles** (`.message` / `.bubble`)
- Container: column flex, gap 8px, padding `14px 10px`, chat bg `--wa-bg` with 1px dot pattern (`radial-gradient(circle at 1px 1px, rgb(0 0 0 / 4%) 1px, transparent 0)` at 16–18px tile)
- Bot (assistant): `align-self: flex-start`, radius `10px 10px 10px 2px`, bg `--wa-in`, color `--wa-ink`, shadow `0 1px 1px rgb(11 20 26 / 13%)`
- Guest (user): `align-self: flex-end`, radius `10px 10px 2px 10px`, bg `--wa-out`
- Text: `.85rem / 1.6`, `overflow-wrap: anywhere`; timestamp `.59rem`, `--wa-muted`, tabular-nums, right-aligned
- Entry animation: `message-in .28s cubic-bezier(.2,.8,.3,1)`
- Mini phone variant `.hc`: padding `7px 10px`, radius `9px 9px 9px 2px` / `9px 9px 2px 9px`, font `.7rem/1.45`

**Status dot** (`.status-dot`, `.live-dot`)
- Default: `7px` circle, bg `--wa-muted`
- Ready: bg `#25d366` + `0 0 0 3px rgb(37 211 102 / 18%)` ring
- Live card variant `.live-dot`: `9px`, `--line` default; `.is-ok` → `--ok` + ring `color-mix(--ok 20%)`; `.is-error` → `--error` + ring

**Badges / labels** (landing)
- `.pill`: padding `6px 12px`, radius `999px`, border `1px solid var(--line)`, bg `--card`, color `--accent`, `.72rem`/600
- `.arguments span`: mono chip, padding `3px 7px`, radius 6px, border `1px solid var(--line)`, color `--muted`, `.63rem`
- `.event-source`: dashed border pill, padding `3px 9px`, `--muted`, `.62rem`
- `.chip` (3D float): mono `.64rem`, padding `7px 11px`, radius `999px`, glassy `color-mix(--card 86%)` + blur

**Panel rows / table rows** (landing availability list)
- `.availability-list li`: grid `minmax(0,1fr) auto`, gap `2px 12px`, `padding-top: 8px`, `border-top: 1px solid var(--line-soft)` between rows (none on first); label `.76rem`, strong `--ink`, meta `--muted`, total `--ink`/600 right-aligned
- `.step` rows: grid `62px 1fr`, gap 18px, `padding: 20px 0`, `border-top: 1px solid var(--line)` (last also bottom)
- `.voice-line`: padding `10px 14px`, radius 12px, bg `--card-2`; `.guest` variant `color-mix(--accent 10%, --card-2)`

**Other landing states**
- Error: `.notice.error`/`.chat-error` — bg `--error-bg`, color `--error`, retry button outlined `currentColor` pill
- Success ticket: `.booking-ticket` — bg `--ok-bg`, border `color-mix(--ok 40%, --line)`, heading `--ok`
- Focus: `:focus-visible` → `outline: 3px solid var(--accent); outline-offset: 3px; border-radius: 4px`

### Panel

**Skeleton loader** (`.skeleton`, `copiloto/.../theme.css`)
- Radius 8px, `linear-gradient(90deg, var(--card-2) 25%, var(--card) 37%, var(--card-2) 63%)`, background-size 200%, `shimmer 1.4s linear infinite`

**Entrance animations**: `.rise` / `.pop` — `.42s`/`.5s var(--ease) both`, stagger `calc(var(--i, 0) * 60ms)`

The panel stylesheet defines **no** buttons, cards, rows, or tables — those components live in the panel templates, outside these two sources, and are therefore not recorded here.

---

## 9. What is NOT defined in the sources

- **Spacing scale** — no tokens in either file (raw values only)
- **Radius scale** — no tokens
- **Panel component rules** (buttons, cards, rows) — not in `theme.css`
- **Panel mono font stack** — not declared
- **Panel heading sizes** — family/weight only, no size
- **Panel spacing/typography beyond body 14px/1.5** — none
