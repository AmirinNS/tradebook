---
slug: macd
title: "MACD: Momentum and Trend Convergence"
order: 4
summary: "Combine moving average trend-following with momentum velocity via Gerald Appel's classic oscillator."
reading_time: 5
related_filters:
  - macd_cross_up
---

## The Dual Nature of MACD

Created by Gerald Appel in the late 1970s, the **Moving Average Convergence Divergence (MACD)** is a trend-following momentum indicator. While traditional moving averages lag the market, MACD transforms exponential moving averages into an oscillator that detects changes in momentum, direction, and trend strength.

---

## The Three Components of MACD

The standard configuration uses parameters (12, 26, 9) computed on daily closing prices:

1. **MACD Line (Fast Line)**: The difference between a fast 12-day exponential average and a slower 26-day exponential average:
   ```
   MACD Line = EMA(12) - EMA(26)
   ```
2. **Signal Line (Slow Line)**: A 9-day exponential moving average applied directly to the MACD line:
   ```
   Signal Line = EMA(9, MACD Line)
   ```
3. **MACD Histogram**: Visualizes the distance between the MACD Line and its Signal Line:
   ```
   Histogram = MACD Line - Signal Line
   ```
   When the histogram is positive (above zero), the MACD Line is above its Signal Line.

---

## Key Signals and Interpretations

### 1. Signal Line Crossovers
- **Bullish Crossover**: When the MACD Line crosses above the Signal Line, the histogram flips from negative to positive. This indicates short-term momentum is accelerating faster than medium-term momentum.
- **Bearish Crossover**: When the MACD Line crosses below the Signal Line, the histogram flips negative, signaling that upward momentum is decelerating.

### 2. Centerline (Zero-Line) Crossovers
The zero-line reflects parity between the 12-day and 26-day EMAs:
- A cross above zero confirms that the 12-day EMA is higher than the 26-day EMA, confirming an upward trend.
- A cross below zero confirms that short-term prices are declining below the medium-term average.

### 3. Histogram Contraction
Before a moving average crossover occurs on the chart, the histogram bars begin to shrink toward zero. Monitoring histogram contraction allows traders to anticipate potential momentum shifts before the slower signal line cross completes.

---

## Managing Whipsaws in Range-Bound Markets

Because MACD is derived from moving averages, it functions best in trending markets. In sideways, range-bound markets, the 12-day and 26-day EMAs will frequently entangle, producing false crossover signals (whipsaws). Combining MACD crossovers with a trend filter (such as only taking long signals when price trades above the 200-day SMA) helps avoid choppy traps.

---

## Educational Disclaimer

*Educational content, not financial advice.*

---

## Try It in Tradebook

Identify stocks that just triggered a fresh bullish momentum turn using the screener's MACD crossover filter.

[Screen for stocks with MACD cross up](/screener?macd_cross_up=1)
