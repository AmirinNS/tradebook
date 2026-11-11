---
slug: rsi
title: "RSI: Relative Strength Index"
order: 3
summary: "Understand Wilder's 14-period momentum oscillator, overbought and oversold extremes, and divergence."
reading_time: 5
related_filters:
  - rsi_lt
  - rsi_gt
---

## Measuring Velocity and Momentum

Developed by J. Welles Wilder Jr. in 1978, the **Relative Strength Index (RSI)** is a bounded momentum oscillator ranging between 0 and 100. It measures the velocity and magnitude of recent price changes to evaluate whether an asset is overextended relative to its recent trading range.

---

## The 14-Period Wilder Calculation

RSI evaluates price performance over a standard 14-session lookback window:

1. Separate closing changes into positive gains and negative losses:
   - If Close > Previous Close: Gain = Close − Previous Close, Loss = 0
   - If Close < Previous Close: Gain = 0, Loss = Previous Close − Close
2. Compute the initial 14-day average gain and average loss.
3. For subsequent days, apply Wilder's smoothing technique:

```
Average gain = (previous average gain x 13 + current gain) / 14
Average loss = (previous average loss x 13 + current loss) / 14
RS           = average gain / average loss
RSI          = 100 - (100 / (1 + RS))
```

If an asset records zero losses over 14 sessions, RSI reaches 100. Conversely, continuous uninterrupted losses push RSI to 0.

---

## Overbought and Oversold Benchmarks

- **Overbought (RSI > 70)**: Suggests buyers have pushed prices up with high velocity over the past two weeks. While this indicates powerful momentum, it signals that risk/reward for new long entries is deteriorating as a pullback or consolidation becomes more probable.
- **Oversold (RSI < 30)**: Indicates steep downward momentum where selling pressure has dominated. Value and mean-reversion traders watch for stabilization in this zone for potential exhaustion bottoms.

### The Strong Trend Exception
A critical pitfall in oscillator analysis is assuming an overbought RSI (>70) always triggers an immediate reversal. During strong structural bull runs, RSI can remain pegged above 70 for weeks while prices continue to advance. Conversely, in persistent bear trends, RSI can stay suppressed below 30 without meaningful recovery.

---

## Momentum Divergence

One of the most informative setups on an RSI chart is **divergence** between price action and momentum:

- **Bullish Divergence**: The stock makes a lower price low, but RSI forms a higher low. This indicates that downside selling velocity is waning, suggesting supply exhaustion.
- **Bearish Divergence**: The stock advances to a higher price high, but RSI forms a lower peak. This reveals that the advance is losing underlying momentum, warning of an impending correction.

---

## Educational Disclaimer

*Educational content, not financial advice.*

---

## Try It in Tradebook

Scan for market candidates currently experiencing short-term selling pressure by screening for stocks with RSI under 30.

[Screen for stocks with RSI below 30](/screener?rsi_lt=30)
