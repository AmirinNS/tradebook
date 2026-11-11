---
slug: fifo-and-realized-pnl
title: "FIFO Accounting and Realized P/L"
order: 6
summary: "Understand First-In First-Out lot matching, acquisition fee allocation, and the truth of realized profit."
reading_time: 5
related_filters: []
---

## Why Accounting Methodology Matters

When you buy shares of a company across multiple days at different prices and subsequently sell a portion of your position, which shares did you sell?

To accurately calculate tax liabilities, investment performance, and actual profit, an unambiguous matching convention is required. In Tradebook and standard exchange reporting, trades are matched using the **First-In, First-Out (FIFO)** accounting method.

---

## How FIFO Lot Matching Works

FIFO assumes that the oldest shares purchased are the first ones liquidated when an exit trade occurs.

### Example Walkthrough
1. **Trade 1 (Jan 10)**: Buy 1,000 shares @ RM2.00 (Lot A)
2. **Trade 2 (Jan 15)**: Buy 1,000 shares @ RM3.00 (Lot B)
3. **Trade 3 (Jan 20)**: Sell 1,200 shares @ RM3.50

Under FIFO:
- The first 1,000 shares sold match completely against **Lot A** (@ RM2.00).
- The remaining 200 shares sold match against **Lot B** (@ RM3.00).
- An open remainder of 800 shares from Lot B remains in your portfolio at a cost basis of RM3.00.

---

## Fee Allocation to Cost Basis

A common error in naive portfolio trackers is treating trading fees as an afterthought or ignoring buy fees until cash is drawn. Professional accounting incorporates buy-side fees directly into the **cost basis** of acquired shares:

```
Effective Cost per Share = ((Buy Shares x Buy Price) + Allocated Buy Fees) / Buy Shares
```

When a lot is partially liquidated, its buy fees are apportioned proportionally to the sold shares, while the remaining fee share stays with the open position. Tradebook strictly conserves rounding remainders so that total fees match actual cash paid to the cent.

---

## Realized P/L vs Unrealized P/L

Understanding the distinction between realized and unrealized performance is essential for objective trading evaluation:

1. **Unrealized P/L (Paper Profit/Loss)**:
   ```
   Unrealized P/L = (Current Market Price - Effective Cost per Share) x Open Shares
   ```
   This value fluctuates daily with market ticks and exists only on paper until closed.
2. **Realized P/L (Closed Profit/Loss)**:
   ```
   Realized P/L = (Sell Price x Shares) - (Cost Basis per Share x Shares) - Sell Fees
   ```
   Realized P/L is permanent, cash-settled, and net of both entry and exit transaction fees.

In Tradebook, Realized P/L is the headline figure of your journal because it reflects confirmed equity gains rather than temporary paper fluctuations.

---

## Educational Disclaimer

*Educational content, not financial advice.*

---

## Try It in Tradebook

See FIFO lot matching and fee allocation in action by reviewing the trades and open positions on the demo ledger.

[Inspect realized P/L and closed trades on Demo](/demo)
