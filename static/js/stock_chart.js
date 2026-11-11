// Stock charting with TradingView Lightweight Charts (v4.2.1)
// Synchronized Price (Candles + SMA20/50), RSI (14), and MACD (12/26/9) panes.

(function () {
    "use strict";

    if (typeof LightweightCharts === "undefined") {
        return;
    }

    const wrapper = document.getElementById("chartWrapper");
    if (!wrapper) return;

    const symbol = wrapper.getAttribute("data-symbol");
    if (!symbol) return;

    const priceEl = document.getElementById("priceChart");
    const rsiEl = document.getElementById("rsiChart");
    const macdEl = document.getElementById("macdChart");
    const rsiValueEl = document.getElementById("rsiValue");
    const macdValueEl = document.getElementById("macdValue");

    if (!priceEl || !rsiEl || !macdEl) return;

    function getThemeTokens() {
        const isDark = document.documentElement.getAttribute("data-bs-theme") === "dark";
        return isDark
            ? {
                  pos: "#67DFC0",
                  neg: "#FFA184",
                  accent: "#9FC1FF",
                  muted: "#A9BACB",
                  border: "#728397",
                  divider: "#26323E",
                  grid: "rgba(38, 50, 62, 0.4)",
                  text: "#EDF3F8",
              }
            : {
                  pos: "#006B54",
                  neg: "#B13A26",
                  accent: "#174EA6",
                  muted: "#526171",
                  border: "#7A8796",
                  divider: "#DDE3E9",
                  grid: "rgba(221, 227, 233, 0.6)",
                  text: "#17212B",
              };
    }

    let tokens = getThemeTokens();

    function baseChartOptions(height, showTimeScale) {
        return {
            height: height,
            layout: {
                background: { type: "solid", color: "transparent" },
                textColor: tokens.muted,
                fontFamily: '"IBM Plex Sans", system-ui, sans-serif',
                fontSize: 11,
            },
            grid: {
                vertLines: { color: tokens.grid },
                horzLines: { color: tokens.grid },
            },
            rightPriceScale: {
                borderColor: tokens.divider,
                textColor: tokens.muted,
            },
            timeScale: {
                borderColor: tokens.divider,
                visible: showTimeScale,
                timeVisible: false,
            },
            crosshair: {
                vertLine: {
                    color: tokens.muted,
                    width: 1,
                    style: LightweightCharts.LineStyle.Dotted,
                },
                horzLine: {
                    color: tokens.muted,
                    width: 1,
                    style: LightweightCharts.LineStyle.Dotted,
                },
            },
            handleScroll: { mouseWheel: true, pressedMouseMove: true },
            handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
        };
    }

    const priceChart = LightweightCharts.createChart(priceEl, baseChartOptions(320, false));
    const rsiChart = LightweightCharts.createChart(rsiEl, baseChartOptions(96, false));
    const macdChart = LightweightCharts.createChart(macdEl, baseChartOptions(112, true));

    // Price Chart Series
    const candleSeries = priceChart.addCandlestickSeries({
        upColor: "transparent",
        downColor: tokens.neg,
        borderVisible: true,
        borderUpColor: tokens.pos,
        borderDownColor: tokens.neg,
        wickUpColor: tokens.pos,
        wickDownColor: tokens.neg,
    });

    const sma20Series = priceChart.addLineSeries({
        color: tokens.accent,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
    });

    const sma50Series = priceChart.addLineSeries({
        color: tokens.muted,
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false,
    });

    // RSI Chart Series
    const rsiSeries = rsiChart.addLineSeries({
        color: tokens.accent,
        lineWidth: 1.5,
        priceLineVisible: false,
        lastValueVisible: false,
    });

    rsiSeries.createPriceLine({
        price: 70,
        color: tokens.muted,
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dotted,
        axisLabelVisible: true,
        title: "70",
    });

    rsiSeries.createPriceLine({
        price: 30,
        color: tokens.muted,
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dotted,
        axisLabelVisible: true,
        title: "30",
    });

    // MACD Chart Series
    const macdHistSeries = macdChart.addHistogramSeries({
        priceLineVisible: false,
        lastValueVisible: false,
    });

    const macdLineSeries = macdChart.addLineSeries({
        color: tokens.accent,
        lineWidth: 1.5,
        priceLineVisible: false,
        lastValueVisible: false,
    });

    const macdSignalSeries = macdChart.addLineSeries({
        color: tokens.muted,
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false,
    });

    // Time scale synchronization across all three panes
    let isSyncing = false;
    function syncTimeScales(source, targets) {
        source.timeScale().subscribeVisibleLogicalRangeChange(range => {
            if (isSyncing || !range) return;
            isSyncing = true;
            targets.forEach(t => t.timeScale().setVisibleLogicalRange(range));
            isSyncing = false;
        });
    }

    syncTimeScales(priceChart, [rsiChart, macdChart]);
    syncTimeScales(rsiChart, [priceChart, macdChart]);
    syncTimeScales(macdChart, [priceChart, rsiChart]);

    let barsData = [];
    let currentRange = "6m";

    function applyCurrentRange() {
        if (!barsData || barsData.length === 0) return;
        const total = barsData.length;
        let count = total;
        if (currentRange === "3m") count = Math.min(total, 63);
        else if (currentRange === "6m") count = Math.min(total, 126);
        else if (currentRange === "1y") count = Math.min(total, 252);
        else if (currentRange === "all") count = total;

        const fromIdx = Math.max(0, total - count);
        const toIdx = total - 1;
        const fromTime = barsData[fromIdx].time;
        const toTime = barsData[toIdx].time;

        const charts = [priceChart, rsiChart, macdChart];
        isSyncing = true;
        try {
            charts.forEach(c => {
                try {
                    c.timeScale().setVisibleRange({ from: fromTime, to: toTime });
                } catch (e) {
                    c.timeScale().setVisibleLogicalRange({ from: fromIdx, to: toIdx });
                }
            });
        } finally {
            isSyncing = false;
        }
    }

    // Fetch and populate bar data
    fetch(`/api/stocks/${encodeURIComponent(symbol)}/bars`)
        .then(res => {
            if (!res.ok) throw new Error("Failed to load bars");
            return res.json();
        })
        .then(data => {
            if (!data.bars || data.bars.length === 0) return;

            barsData = data.bars;

            const candleData = [];
            const sma20Data = [];
            const sma50Data = [];
            const rsiData = [];
            const macdHistData = [];
            const macdLineData = [];
            const macdSignalData = [];

            let lastRsi = null;
            let lastMacd = null;

            for (let i = 0; i < barsData.length; i++) {
                const b = barsData[i];
                candleData.push({
                    time: b.time,
                    open: parseFloat(b.open),
                    high: parseFloat(b.high),
                    low: parseFloat(b.low),
                    close: parseFloat(b.close),
                });

                if (b.sma20 !== null) {
                    sma20Data.push({ time: b.time, value: parseFloat(b.sma20) });
                } else {
                    sma20Data.push({ time: b.time });
                }

                if (b.sma50 !== null) {
                    sma50Data.push({ time: b.time, value: parseFloat(b.sma50) });
                } else {
                    sma50Data.push({ time: b.time });
                }

                if (b.rsi !== null) {
                    const r = parseFloat(b.rsi);
                    rsiData.push({ time: b.time, value: r });
                    lastRsi = r;
                } else {
                    rsiData.push({ time: b.time });
                }

                if (b.macd !== null) {
                    const m = parseFloat(b.macd);
                    macdLineData.push({ time: b.time, value: m });
                    lastMacd = m;
                } else {
                    macdLineData.push({ time: b.time });
                }

                if (b.macd_signal !== null) {
                    macdSignalData.push({ time: b.time, value: parseFloat(b.macd_signal) });
                } else {
                    macdSignalData.push({ time: b.time });
                }

                if (b.macd_hist !== null) {
                    const h = parseFloat(b.macd_hist);
                    macdHistData.push({
                        time: b.time,
                        value: h,
                        color: h >= 0 ? tokens.pos : tokens.neg,
                    });
                } else {
                    macdHistData.push({ time: b.time });
                }
            }

            candleSeries.setData(candleData);
            sma20Series.setData(sma20Data);
            sma50Series.setData(sma50Data);
            rsiSeries.setData(rsiData);
            macdHistSeries.setData(macdHistData);
            macdLineSeries.setData(macdLineData);
            macdSignalSeries.setData(macdSignalData);

            if (lastRsi !== null && rsiValueEl) {
                rsiValueEl.textContent = `RSI: ${lastRsi.toFixed(2)}`;
            }
            if (lastMacd !== null && macdValueEl) {
                macdValueEl.textContent = `MACD: ${lastMacd.toFixed(4)}`;
            }

            // Size charts to container and apply initial 6M range
            resizeCharts();
            applyCurrentRange();
            requestAnimationFrame(applyCurrentRange);
            setTimeout(applyCurrentRange, 50);
        })
        .catch(err => {
            console.error("Error loading stock bars:", err);
        });

    function setRange(rangeKey) {
        currentRange = rangeKey;
        applyCurrentRange();
    }

    // Range buttons click handlers
    const rangeBtns = wrapper.querySelectorAll(".range-btn");
    rangeBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            rangeBtns.forEach(b => {
                b.classList.remove("btn-tb");
                b.classList.add("btn-tb-outline");
            });
            btn.classList.remove("btn-tb-outline");
            btn.classList.add("btn-tb");
            setRange(btn.getAttribute("data-range"));
        });
    });

    // Handle Window Resize and Container Sizing
    function resizeCharts() {
        const width = priceEl.clientWidth;
        if (width > 0) {
            priceChart.applyOptions({ width });
            rsiChart.applyOptions({ width });
            macdChart.applyOptions({ width });
            applyCurrentRange();
        }
    }

    if (typeof ResizeObserver !== "undefined") {
        const ro = new ResizeObserver(() => {
            resizeCharts();
        });
        ro.observe(priceEl);
    }

    window.addEventListener("resize", () => {
        resizeCharts();
        requestAnimationFrame(applyCurrentRange);
    });
    setTimeout(resizeCharts, 50);

    // Expose chart references on wrapper for introspection
    wrapper._priceChart = priceChart;
    wrapper._rsiChart = rsiChart;
    wrapper._macdChart = macdChart;
    wrapper._getRange = () => currentRange;
    wrapper._getBarsData = () => barsData;
    wrapper._applyCurrentRange = applyCurrentRange;

    // Dynamic Theme Updating
    window.addEventListener("themechange", () => {
        tokens = getThemeTokens();

        const commonOptions = {
            layout: {
                textColor: tokens.muted,
            },
            grid: {
                vertLines: { color: tokens.grid },
                horzLines: { color: tokens.grid },
            },
            rightPriceScale: {
                borderColor: tokens.divider,
                textColor: tokens.muted,
            },
            timeScale: {
                borderColor: tokens.divider,
            },
        };

        priceChart.applyOptions(commonOptions);
        rsiChart.applyOptions(commonOptions);
        macdChart.applyOptions(commonOptions);

        candleSeries.applyOptions({
            borderUpColor: tokens.pos,
            borderDownColor: tokens.neg,
            wickUpColor: tokens.pos,
            wickDownColor: tokens.neg,
            downColor: tokens.neg,
        });

        sma20Series.applyOptions({ color: tokens.accent });
        sma50Series.applyOptions({ color: tokens.muted });
        rsiSeries.applyOptions({ color: tokens.accent });
        macdLineSeries.applyOptions({ color: tokens.accent });
        macdSignalSeries.applyOptions({ color: tokens.muted });
    });
})();
