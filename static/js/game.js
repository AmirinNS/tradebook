/**
 * Tycoon Market Game Controller (Direction A)
 * Vanilla JS, no external libraries. Handles game HUD, trading, loan repayment,
 * day advancement, and optimistic concurrency version tracking.
 */
(function() {
    'use strict';

    const appEl = document.getElementById('gameApp');
    if (!appEl) return;

    const gameId = appEl.dataset.gameId;
    let currentVersion = parseInt(appEl.dataset.version, 10) || 1;
    const csrfToken = appEl.dataset.csrf;

    const initialDataEl = document.getElementById('initialGameData');
    let state = initialDataEl ? JSON.parse(initialDataEl.textContent) : null;
    if (!state) return;

    // Elements
    const dayLabel = document.getElementById('dayLabel');
    const gameAlert = document.getElementById('gameAlert');
    const gameAlertMsg = document.getElementById('gameAlertMsg');
    const cashMetric = document.getElementById('cashMetric');
    const principalMetric = document.getElementById('principalMetric');
    const interestMetric = document.getElementById('interestMetric');
    const netWorthMetric = document.getElementById('netWorthMetric');
    const boardBody = document.getElementById('boardBody');
    const holdingsBody = document.getElementById('holdingsBody');
    const holdingsTable = document.getElementById('holdingsTable');
    const noHoldingsMsg = document.getElementById('noHoldingsMsg');
    const newsText = document.getElementById('newsText');
    const endScreen = document.getElementById('endScreen');
    const finalScoreVal = document.getElementById('finalScoreVal');
    const actionControls = document.getElementById('actionControls');

    // Trade form elements
    const tradeForm = document.getElementById('tradeForm');
    const tradeSymbol = document.getElementById('tradeSymbol');
    const sideBuy = document.getElementById('sideBuy');
    const sideSell = document.getElementById('sideSell');
    const tradeQty = document.getElementById('tradeQty');
    const tradeEstTotal = document.getElementById('tradeEstTotal');
    const tradeMaxHint = document.getElementById('tradeMaxHint');
    const tradeSubmitBtn = document.getElementById('tradeSubmitBtn');

    // Repay form elements
    const repayForm = document.getElementById('repayForm');
    const repayAmount = document.getElementById('repayAmount');
    const repayMaxBtn = document.getElementById('repayMaxBtn');
    const repaySubmitBtn = document.getElementById('repaySubmitBtn');
    const debtTotalHint = document.getElementById('debtTotalHint');

    // Advance button
    const nextDayBtn = document.getElementById('nextDayBtn');

    // Helper: format numbers
    function fmt(val, d = 2) {
        const num = typeof val === 'string' ? parseFloat(val) : Number(val);
        if (isNaN(num)) return '0.00';
        return num.toLocaleString('en-US', {
            minimumFractionDigits: d,
            maximumFractionDigits: d,
        });
    }

    function pl(n, d = 2) {
        const num = typeof n === 'string' ? parseFloat(n) : Number(n);
        if (num > 0.00001) {
            return `<span class="tb-pos"><span aria-hidden="true">▲</span> +${fmt(num, d)}<span class="visually-hidden"> gain</span></span>`;
        }
        if (num < -0.00001) {
            return `<span class="tb-neg"><span aria-hidden="true">▼</span> ${fmt(num, d)}<span class="visually-hidden"> loss</span></span>`;
        }
        return `<span>${fmt(0, d)}</span>`;
    }

    function showAlert(message) {
        if (!gameAlert) return;
        gameAlertMsg.textContent = message;
        gameAlert.classList.remove('d-none');
        gameAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function clearAlert() {
        if (!gameAlert) return;
        gameAlert.classList.add('d-none');
        gameAlertMsg.textContent = '';
    }

    function setBusy(busy) {
        [tradeSubmitBtn, repaySubmitBtn, nextDayBtn, repayMaxBtn].forEach(btn => {
            if (btn) btn.disabled = busy || state.finished;
        });
    }

    // Render Metric HUD
    function renderHUD() {
        if (dayLabel) {
            dayLabel.textContent = `Day ${String(state.day).padStart(2, '0')} / 30`;
        }
        if (cashMetric) cashMetric.textContent = `MYR ${fmt(state.cash)}`;
        if (principalMetric) principalMetric.textContent = `MYR ${fmt(state.principal)}`;
        if (interestMetric) interestMetric.textContent = `MYR ${fmt(state.interest)}`;
        if (netWorthMetric) netWorthMetric.textContent = `MYR ${fmt(state.net_worth)}`;
    }

    // Render Market Board
    function renderBoard() {
        if (!boardBody) return;
        boardBody.innerHTML = state.companies.map(co => {
            const sym = co.symbol;
            const price = parseFloat(co.price);
            const held = state.holdings[sym] || 0;

            let changeHtml = '<span class="tb-muted">N/A</span>';
            if (state.day > 1 && state.history && state.history[sym] && state.history[sym].length >= 2) {
                const hist = state.history[sym];
                const prevPrice = parseFloat(hist[hist.length - 2]);
                const diff = price - prevPrice;
                changeHtml = pl(diff, 4);
            }

            return `<tr>
                <td class="fw-semibold">
                    <span class="d-block">${co.name}</span>
                    <span class="tb-context">${co.symbol}</span>
                </td>
                <td class="tb-muted">${co.sector}</td>
                <td class="r tb-num">${fmt(price, 4)}</td>
                <td class="r tb-num">${changeHtml}</td>
                <td class="r tb-num fw-medium">${held.toLocaleString('en-US')}</td>
            </tr>`;
        }).join('');
    }

    // Render Holdings Table
    function renderHoldings() {
        const heldEntries = Object.entries(state.holdings).filter(([_, qty]) => qty > 0);
        if (heldEntries.length === 0) {
            if (holdingsTable) holdingsTable.classList.add('d-none');
            if (noHoldingsMsg) noHoldingsMsg.classList.remove('d-none');
            return;
        }

        if (holdingsTable) holdingsTable.classList.remove('d-none');
        if (noHoldingsMsg) noHoldingsMsg.classList.add('d-none');

        const companyMap = {};
        state.companies.forEach(c => { companyMap[c.symbol] = c; });

        holdingsBody.innerHTML = heldEntries.map(([sym, qty]) => {
            const co = companyMap[sym] || { name: sym, price: 0 };
            const curPrice = parseFloat(co.price);
            const posVal = curPrice * qty;
            return `<tr>
                <td class="fw-semibold">${sym}</td>
                <td class="tb-muted">${co.name}</td>
                <td class="r tb-num">${qty.toLocaleString('en-US')}</td>
                <td class="r tb-num">${fmt(curPrice, 4)}</td>
                <td class="r tb-num fw-medium">MYR ${fmt(posVal, 2)}</td>
            </tr>`;
        }).join('');
    }

    // Render News Box
    function renderNews() {
        if (!newsText) return;
        if (state.news && state.news.length > 0) {
            const latest = state.news[state.news.length - 1];
            newsText.textContent = `Day ${latest.day}: ${latest.headline}`;
        } else {
            newsText.textContent = 'Day 1: Simulation begins. Prices move from tomorrow.';
        }
    }

    // Render Trade Form Controls
    function renderTradeForm() {
        if (!tradeSymbol) return;
        const currentSelected = tradeSymbol.value;
        tradeSymbol.innerHTML = state.companies.map(co => {
            const selected = co.symbol === currentSelected ? 'selected' : '';
            return `<option value="${co.symbol}" ${selected}>${co.name} (${co.symbol}) — MYR ${fmt(co.price, 4)}</option>`;
        }).join('');

        updateTradeEstimate();
    }

    function updateTradeEstimate() {
        if (!tradeSymbol || !tradeQty) return;
        const sym = tradeSymbol.value;
        const co = state.companies.find(c => c.symbol === sym);
        if (!co) return;

        const price = parseFloat(co.price);
        const qty = parseInt(tradeQty.value, 10) || 0;
        const total = price * qty;
        if (tradeEstTotal) {
            tradeEstTotal.textContent = `MYR ${fmt(total, 2)}`;
        }

        const isBuy = sideBuy && sideBuy.checked;
        const held = state.holdings[sym] || 0;
        const cash = parseFloat(state.cash) || 0;

        if (isBuy) {
            const maxShares = price > 0 ? Math.floor(cash / price) : 0;
            if (tradeMaxHint) {
                tradeMaxHint.textContent = `Max affordable: ${maxShares.toLocaleString('en-US')}`;
            }
        } else {
            if (tradeMaxHint) {
                tradeMaxHint.textContent = `Held: ${held.toLocaleString('en-US')}`;
            }
        }
    }

    // Render Repay Form Controls
    function renderRepayForm() {
        const totalDebt = parseFloat(state.debt) || 0;
        if (debtTotalHint) {
            debtTotalHint.textContent = `Total debt: MYR ${fmt(totalDebt)}`;
        }
        if (repaySubmitBtn && repayAmount) {
            const debtRemaining = totalDebt > 0;
            repaySubmitBtn.disabled = !debtRemaining || state.finished;
            repayAmount.disabled = !debtRemaining || state.finished;
            if (repayMaxBtn) repayMaxBtn.disabled = !debtRemaining || state.finished;
        }
    }

    // Render End Screen
    function renderEndScreen() {
        if (state.finished) {
            if (endScreen) {
                endScreen.classList.remove('d-none');
                if (finalScoreVal) {
                    finalScoreVal.textContent = `MYR ${fmt(state.score || state.net_worth)}`;
                }
            }
            if (actionControls) {
                actionControls.classList.add('opacity-50');
            }
            if (nextDayBtn) nextDayBtn.disabled = true;
            if (tradeSubmitBtn) tradeSubmitBtn.disabled = true;
            if (repaySubmitBtn) repaySubmitBtn.disabled = true;
        } else {
            if (endScreen) endScreen.classList.add('d-none');
            if (actionControls) actionControls.classList.remove('opacity-50');
        }
    }

    function renderAll() {
        renderHUD();
        renderBoard();
        renderHoldings();
        renderNews();
        renderTradeForm();
        renderRepayForm();
        renderEndScreen();
    }

    // API Action Dispatcher
    async function sendAction(actionObj) {
        setBusy(true);
        try {
            const response = await fetch(`/api/play/${encodeURIComponent(gameId)}/action`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
                body: JSON.stringify({
                    action: actionObj,
                    version: currentVersion,
                }),
            });

            if (response.status === 200) {
                const data = await response.json();
                if (data.version) {
                    currentVersion = data.version;
                }
                state = data;
                clearAlert();
                renderAll();
            } else if (response.status === 409) {
                showAlert('That action was not applied. The game moved on in another tab. Reload to see the current day. Nothing was charged twice.');
            } else if (response.status === 400) {
                const errData = await response.json().catch(() => ({}));
                showAlert(errData.error || errData.message || 'The action could not be completed.');
            } else if (response.status === 404) {
                showAlert('Game session not found or you do not own this game.');
            } else {
                showAlert(`Server returned an error (${response.status}). Please try again.`);
            }
        } catch (err) {
            showAlert('Network communication error. Please check your connection and try again.');
        } finally {
            setBusy(false);
        }
    }

    // Attach Event Listeners
    if (tradeForm) {
        tradeForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const symbol = tradeSymbol.value;
            const side = sideBuy && sideBuy.checked ? 'buy' : 'sell';
            const qty = parseInt(tradeQty.value, 10);
            if (!symbol || !qty || qty <= 0) {
                showAlert('Please choose a company and enter a positive integer of shares.');
                return;
            }
            sendAction({ type: side, symbol: symbol, qty: qty });
        });
    }

    if (tradeSymbol) tradeSymbol.addEventListener('change', updateTradeEstimate);
    if (tradeQty) tradeQty.addEventListener('input', updateTradeEstimate);
    if (sideBuy) sideBuy.addEventListener('change', updateTradeEstimate);
    if (sideSell) sideSell.addEventListener('change', updateTradeEstimate);

    if (repayForm) {
        repayForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const amountVal = repayAmount.value.trim();
            if (!amountVal || parseFloat(amountVal) <= 0) {
                showAlert('Enter a positive repayment amount.');
                return;
            }
            sendAction({ type: 'repay', amount: amountVal });
            repayAmount.value = '';
        });
    }

    if (repayMaxBtn) {
        repayMaxBtn.addEventListener('click', function() {
            const cash = parseFloat(state.cash) || 0;
            const debt = parseFloat(state.debt) || 0;
            const maxRepay = Math.max(0, Math.min(cash, debt));
            if (repayAmount) {
                repayAmount.value = maxRepay.toFixed(2);
            }
        });
    }

    if (nextDayBtn) {
        nextDayBtn.addEventListener('click', function(e) {
            e.preventDefault();
            sendAction({ type: 'next_day' });
        });
    }

    // Initial render
    renderAll();
})();
