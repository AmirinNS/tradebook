---
slug: bursa-trading-costs
title: "Bursa Malaysia Trading Costs and Fee Breakdown"
order: 7
summary: "Understand brokerage commissions, clearing fees, stamp duty tiers, and calculate trade break-even hurdles."
reading_time: 6
related_filters: []
---

## The True Cost of Executing Trades

Every transaction executed on Bursa Malaysia incurs regulatory and brokerage fees. When trading frequently or with modest capital, frictional costs can compound rapidly, creating a high break-even hurdle before a position generates net profit.

Tradebook calculates and models these costs using the dated schedule defined in `sources/fee_schedule.py` (checked **2026-11-11**, reference source: [Rakuten Trade Fee Schedule](https://www.rakutentrade.my/fees)).

---

## The Four Components of Bursa Transaction Fees

When buying or selling ordinary listed shares on Bursa Malaysia, four potential fee layers apply:

### 1. Brokerage Fee (Commission)
The fee paid to your participating broker for executing the order:
- **Typical Online Discount Rate**: Frequently around **0.10%** (0.001) of the contract value.
- **Minimum Brokerage**: Most retail brokers enforce a minimum execution fee (e.g. **RM2.88** or RM8.00–RM12.00 depending on account type). On small trades, this minimum floor significantly increases your percentage cost of entry.

### 2. Clearing Fee (Bursa Malaysia Securities Clearing)
A regulatory clearing fee paid to Bursa Malaysia:
- **Rate**: **0.03%** (0.0003) of gross contract value.
- **Cap**: Capped at a maximum of **RM1,000.00** per contract.

### 3. Stamp Duty
A statutory duty levied by the Malaysian Inland Revenue Board (LHDN):
- **Rate**: **RM1.00 for every RM1,000.00** (or fractional portion thereof) of contract value.
- **Rounding Rule**: Fractions round up using ceiling logic (e.g., a contract value of RM2,050 incurs RM3.00 stamp duty because it crosses into the 3rd thousand-ringgit bracket).
- **Cap**: Capped at a maximum of **RM1,000.00** per contract.

### 4. Sales and Service Tax (SST)
Under current regulatory guidelines:
- For **ordinary listed equity shares**, brokerage and clearing services are not subject to SST.
- Note: From 1 October 2025, an 8% SST rate covers brokerage and clearing fees for REITs, ETFs, rights, and structured warrants, but standard ordinary shares remain exempt.

---

## Round-Trip Friction and the Break-Even Hurdle

Because fees apply on **both the buy and sell sides** (a round trip), your stock must rise enough to absorb two sets of brokerage, clearing, and stamp duty charges before you record a positive Realized P/L:

### Case Study: Small Order Friction
- **Capital**: RM1,000 purchase of 1,000 shares @ RM1.00
- **Buy Fees**:
  - Brokerage: RM2.88 (minimum applies, as 0.10% of RM1,000 is only RM1.00)
  - Clearing: RM0.30 (0.03% of RM1,000)
  - Stamp Duty: RM1.00 (1 bracket of RM1,000)
  - Total Buy Fees = RM4.18 (0.42% friction on entry alone)
- **Round-Trip Cost**: Approximately **RM8.36** (~0.84% of position value)

If you exit at RM1.01 (+1.00% gross gain = RM10.00), after subtracting RM8.36 in round-trip fees, your net gain is a mere RM1.64.

Understanding your fee schedule helps you avoid over-trading small positions where transaction friction erodes returns.

---

## Educational Disclaimer

*Educational content, not financial advice.*

---

## Try It in Tradebook

Inspect how actual and estimated fees are deducted from gross returns on every recorded transaction.

[Review fee tracking in the Demo Journal](/demo)
