# DESIGN.md: tradebook

Direction **A, Exchange ledger**, approved 2026-11-11. A precise working ledger: calm for journaling, dense enough to show market fluency. Bootstrap 5.3 (CDN) customized through CSS variables in `static/css/theme.css`. No other CSS or JS framework.

Reference prototype: `design/tradebook-v1/prototype/index.html` (serve the folder and open `?variant=a`). Decisions and states: `design/tradebook-v1/DECISIONS.md`.

## Tokens

| Token | Light | Dark | Use |
|---|---|---|---|
| `--tb-canvas` | #F3F5F7 | #10171F | Page background |
| `--tb-surface` | #FFFFFF | #18232E | Panels, navbar |
| `--tb-text` | #17212B | #EDF3F8 | Body text |
| `--tb-muted` | #526171 | #A9BACB | Labels, context lines |
| `--tb-accent` | #174EA6 | #9FC1FF | Links, primary buttons, active nav, SMA20 |
| `--tb-on-accent` | #FFFFFF | #18232E | Text on accent buttons |
| `--tb-pos` | #006B54 | #67DFC0 | Gains only |
| `--tb-neg` | #B13A26 | #FFA184 | Losses only (never form errors) |
| `--tb-border` | #7A8796 | #728397 | Control borders (3:1+) |
| `--tb-divider` | #DDE3E9 | #26323E | Table and panel separators |

All text and P/L pairs exceed 4.5:1 on surface and canvas (calculated in the Codex critique). Dark mode uses `[data-bs-theme="dark"]` on `<html>`.

Map to Bootstrap: `--bs-body-bg`, `--bs-body-color`, `--bs-secondary-color`, `--bs-border-color`, `--bs-link-color` (and the matching `-rgb` variables), plus component `--bs-btn-*` and `.table` variables.

## Type

- IBM Plex Sans for headings and UI (600 headings, 400/500 body). IBM Plex Mono for numeric values in tables and metrics only, never in prose or dates.
- Scale: 32 (one headline number per screen), 24 (page title), 22 (secondary metrics), 16 (body), 14 (tables), 13 (labels, context lines).
- Numbers: `font-variant-numeric: tabular-nums lining-nums`, right-aligned with right-aligned headings. Prices 4 dp, money 2 dp, shares integers.

## Shape and density

- Spacing on a 4/8 scale. Panel padding 16 px, section gap 24 px, 1280 px max workspace.
- Table rows 40 px, 48 px when they hold actions.
- Radius 4 px on controls, 8 px on panels. No shadows on panels; dropdowns and modals use `0 8px 24px rgb(0 0 0 / 16%)`.
- Buttons at least 44 px tall. Focus is a 2 px accent outline with 2 px offset.
- Active nav: 600 weight plus a 2 px accent underline.

## Financial display rules

- P/L always shows a sign plus ▲ or ▼ and screen-reader text "gain" or "loss". Zero is neutral `0.00`. Missing prices show "No price", never zero.
- Gain and loss colours apply to changes only, not to every price.
- Every screen states its currency and data date in a context line under the title. The "Synthetic demo data" label stays visible on demo and synthetic screens.
- One currency per portfolio. Never add MYR and USD.
- The dominant number is realized P/L. No "account value" headline (not supported by the journal model).
- Wide tables sit in labeled horizontal scroll regions on phones. Never shrink numbers to fit.
- Charts: hollow up candles and filled down candles in pos/neg colours, SMA20 solid accent, SMA50 dashed muted. Show the chart library's NOTICE attribution.

## Components

Navbar with Journal, Stocks, Screener, Learn, Play. Metric card (label, value, context line). Panel with head (title left, context or action right). Data table. Read-only demo banner (accent-tinted surface, eye icon). Context line. Outline and solid accent buttons.

## Decision log

- 2026-11-11: Codex critique proposed A (Exchange ledger), B (Open journal), C (Market bulletin). The user compared A and B in a clickable prototype and chose A.
- 2026-11-11: Public read-only `/demo` shows the seeded synthetic portfolio with a banner. Write controls are replaced by a "Create an account" note.

## Likes / dislikes

- Likes: A's precision and density; financial-workstation feel.
- Dislikes: none recorded yet.
