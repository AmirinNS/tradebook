# Design decisions: tradebook v1 (approved)

Approved variant: **Direction A, Exchange ledger** (2026-11-11). Prototype: `design/tradebook-v1/prototype/index.html?variant=a`. Tokens and rules: `DESIGN.md`. Phases B to G build to this file.

| # | Decision | Why | Alternative considered | Trade-off |
|---|---|---|---|---|
| 1 | Read-only demo banner above the page title on `/demo` | Recruiters arrive without an account; the banner says the data is synthetic and safe | Footer note | Uses one line of the first viewport |
| 2 | Page title plus one context line (currency, price date, period) | Traders must know which currency and day the numbers describe | Title only | More header text |
| 3 | Four-card metric strip; realized P/L is the only 32 px number | It is the result the journal can state with certainty; the strip scans in one glance | Summary rail (B); account value headline | Less room for explanations |
| 4 | Dense 40 px rows, mono tabular numbers, right-aligned, price date column | Traders compare many rows; aligned decimals make differences readable | Card list | Tables scroll horizontally on phones |
| 5 | Stock page leads with symbol, last close, change, and data date, then price, RSI, MACD panes on one time axis | Core job is checking one stock fast; dated, adjusted-data notes avoid false precision | Hero chart without numbers; chart guide panel (B) | Explanations live in Learn links instead of a side panel |
| 6 | Game reuses metric cards and tables; cash, principal, interest, net worth always visible; Next day is the primary action | One design system; borrowed money is never hidden | Separate game skin; "Your money" block (B) | Less playful |
| 7 | Demo dashboard replaces Import and Add trade with "Read-only. Create an account to add or import trades." | Disabled buttons look broken; the note explains why and points to sign-up | Disabled buttons | One less visual anchor at the top right |

## States

- **Dashboard:**
  - Empty: "No trades yet" with Import CSV and Add first trade.
  - Price error: alert saying positions show "No price" until refresh, trades unaffected.
  - Missing price per row: "No price".
- **Stock page:**
  - No data: "No price data for this symbol yet" with a refresh hint.
  - Loading: skeleton panes at the chart heights (320, 96, 112 px).
- **Game:**
  - Day 1 shows changes as N/A.
  - Version conflict: alert "That action was not applied... Nothing was charged twice."
  - Day 30 replaces Next day with the final score.
- **Forms:**
  - Validation errors sit under the field and keep entered values.
  - Submit buttons show a spinner and stay disabled until the response.
- **Keyboard:** skip link to main; visible 2 px focus; the nav toggler is labeled with `aria-controls` and `aria-expanded`.

## Open questions

- Screener table layout: build in Phase D to the same table component; no prototype planned.
- Lesson page typography: Phase F uses body 16 px, max 70ch measure.

Next: `frontend-design` (with `frontend-bootstrap-evolution`) builds these screens in Phases B to G from this file.
