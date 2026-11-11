---
slug: moving-averages
title: "Moving Averages: SMA and EMA"
order: 2
summary: "Smooth price noise, identify trend direction, observe dynamic support, and interpret crossovers."
reading_time: 5
related_filters:
  - above_sma200
---

## Filtering Market Noise

Financial markets are inherently noisy, with daily price fluctuations often obscuring the underlying trajectory. A **Moving Average (MA)** smooths out these erratic fluctuations by calculating the average closing price over a specified number of sessions.

As new data arrives, the oldest price is dropped from the calculation, creating a continuous line that tracks price movement over time.

---

## SMA vs EMA: Speed vs Stability

Two common moving averages are used in market analysis:

### 1. Simple Moving Average (SMA)
The SMA computes an unweighted arithmetic mean over N periods:

```
SMA = (Price_1 + Price_2 + ... + Price_N) / N
```

Every day in the lookback window receives equal weight. The advantage is stability and resistance to false spikes; the disadvantage is that it lags behind recent price shifts.

### 2. Exponential Moving Average (EMA)
The EMA applies a weighting factor that decreases exponentially with time, placing greater emphasis on recent closing prices:

```
Multiplier = 2 / (N + 1)
EMA = (Current Close x Multiplier) + (Previous EMA x (1 - Multiplier))
```

Because it reacts faster to price turns, short-term traders often rely on the 9-day or 21-day EMA. However, faster reaction speed also increases the rate of whipsaws during choppy consolidation.

---

## Benchmark Timeframes

In institutional and technical trading, three time horizons are standard:

- **20-Day MA**: Reflects short-term monthly momentum. When price holds above the rising 20 MA, near-term momentum is constructive.
- **50-Day MA**: Intermediate trend benchmark. Institutional fund managers frequently look to buy pullbacks toward a rising 50-day average.
- **200-Day MA**: Macro bull/bear health indicator. Institutional investors generally distinguish long-term uptrends from secular bear markets by checking whether a stock trades above or below its 200-day SMA.

---

## Crossovers and Trend Filters

Moving averages serve two main purposes:

1. **Trend Filters**: Using moving averages to prevent trading against the macro trend. For example, filtering out all stocks trading below their 200-day SMA ensures you only consider candidates with sustained institutional accumulation.
2. **Crossovers**:
   - **Golden Cross**: A shorter-term moving average (e.g. 50-day SMA) crosses above a longer-term moving average (e.g. 200-day SMA), signaling potential long-term trend transition to the upside.
   - **Death Cross**: A shorter-term moving average crosses below a longer-term moving average, indicating persistent structural selling pressure.

Because moving averages are lagging indicators, crossovers confirm existing trends rather than predicting precise turning points.

---

## Educational Disclaimer

*Educational content, not financial advice.*

---

## Try It in Tradebook

Filter our entire universe for companies demonstrating macro trend health by screening for prices trading above the 200-day SMA.

[Filter screener by Above SMA200](/screener?above_sma200=1)
