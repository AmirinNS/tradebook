---
slug: position-sizing
title: "Position Sizing and Risk Management"
order: 5
summary: "Calculate position size from stop-loss distance, manage risk per trade, and protect against catastrophic drawdowns."
reading_time: 5
related_filters: []
---

## The Mathematics of Capital Preservation

In trading, profitability is not determined by your accuracy rate alone; it is dictated by how much capital you lose when you are wrong versus how much you make when you are right. The primary mechanism for controlling loss magnitude is **position sizing**.

Traders who risk an arbitrary dollar sum or simply invest "whatever cash is available" expose their portfolios to the risk of ruin.

---

## Fixed Fractional Risk: The 1% Rule

Professional risk management begins with defining the maximum percentage of your total account equity you are willing to lose on a single trade. A disciplined standard is **1% to 2%** of account equity:

```
Dollar Risk = Account Equity x Risk Percentage
```

For example, on an account with RM20,000 equity, a 1% risk limit caps the maximum allowable loss on any individual position at **RM200**.

---

## Calculating Shares from Stop-Loss Distance

Position size must be derived backwards from your technical invalidation level (stop-loss), not your target profit:

1. **Identify Entry Price**: Where you plan to buy.
2. **Determine Stop-Loss Price**: The price level where your trade thesis is proven wrong (e.g. below support or recent swing low).
3. **Risk per Share**: The distance between Entry and Stop:
   ```
   Risk per Share = Entry Price - Stop Price
   ```
4. **Position Size (Quantity)**:
   ```
   Shares = Dollar Risk / Risk per Share
   ```

### Concrete Example
- Account Equity: RM50,000
- 1% Max Risk: RM500
- Desired Stock: RM5.00 entry
- Logical Stop-Loss: RM4.50 (Risk per share = RM0.50)
- Calculation: Shares = RM500 / RM0.50 = 1,000 shares
- Total Capital Committed: 1,000 shares x RM5.00 = RM5,000 (10% of total capital, but strictly 1% risk).

If the stop-loss is wider (e.g., RM1.00 per share), the position size automatically shrinks to 500 shares. Sizing by stop distance ensures that no matter how volatile the asset, your dollar loss remains fixed.

---

## Asymmetric Drawdown Recovery

Capital protection is vital because the math of recovery is inherently non-linear:

| Portfolio Loss | Required Gain to Break Even |
|---|---|
| -10% | +11.1% |
| -20% | +25.0% |
| -30% | +42.9% |
| -50% | +100.0% |
| -75% | +300.0% |

A 10% drawdown requires an 11% return to recover. But a 50% drawdown requires a 100% gain just to return to starting capital—a hurdle that takes years or forces reckless risk-taking. Maintaining strict position sizing prevents deep drawdowns.

---

## Educational Disclaimer

*Educational content, not financial advice.*

---

## Try It in Tradebook

Observe how positions and portfolio cash are balanced across multiple trades in the demo journal.

[View risk and position weights on Demo Journal](/demo)
