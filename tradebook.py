# Standard library
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO

# Third-party
from flask import (
    Flask,
    Request,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf import CSRFProtect
from pymongo.errors import DuplicateKeyError, PyMongoError
from waitress import serve

# Local
import modules.calendar as journal_calendar
import modules.csv_import as csv_import
import modules.fees as fees
import modules.imports as imports
import modules.indicators as indicators
import modules.lessons as lessons
import modules.pdf_import as pdf_import
import modules.portfolios as portfolios
import modules.prices as prices
import modules.progress as progress
import modules.screener as screener_module
import modules.trades as trades
import modules.users as users
import sources.money as money
import sources.seo as seo
import sources.universe as universe
from modules.pnl import fifo_positions
from sources.auth import User, init_login, safe_next
from sources.config import (
    APP_ENV,
    COOKIE_SECURE,
    DEBUG,
    DEMO_USER_EMAIL,
    IS_PRODUCTION,
    PORT,
    RATELIMIT_ENABLED,
    SECRET_KEY,
    SITE_URL,
    db,
)
from sources.errors import init_errors
from sources.indexes import ensure_all_indexes


class MemoryUploadRequest(Request):
    """Keep multipart uploads in memory instead of Werkzeug's disk spool."""

    def _get_file_stream(
        self, total_content_length, content_type, filename=None, content_length=None,
    ):
        return BytesIO()


app = Flask(__name__)
app.request_class = MemoryUploadRequest
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=COOKIE_SECURE,
    REMEMBER_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SAMESITE="Lax",
    REMEMBER_COOKIE_SECURE=COOKIE_SECURE,
    RATELIMIT_ENABLED=RATELIMIT_ENABLED,
    MAX_CONTENT_LENGTH=pdf_import.MAX_BYTES + 64 * 1024,
)
init_errors(app)  # themed error pages for every HTTP status
init_login(app)
csrf = CSRFProtect(app)
# shortcut: per-process limits; use shared storage if multiple web processes are needed.
limiter = Limiter(
    key_func=get_remote_address, app=app, storage_uri="memory://", headers_enabled=True
)
ensure_all_indexes(db)


@app.context_processor
def inject_globals():
    # Available in every template (footer year + baseline SEO meta).
    ctx = {"current_year": datetime.now(timezone.utc).year}
    ctx.update(seo.default_meta())
    return ctx


@app.template_filter("fmt_money")
def fmt_money_filter(value, dp=2):
    """Format a monetary or price value with thousands separators.

    dp=2 for money (default), dp=4 for prices.
    """
    if value is None or value == "":
        return "—"
    try:
        val_str = str(value).strip().replace(",", "")
        d = Decimal(val_str)
        if dp == 4:
            d_rounded = money.price(d)
            return f"{d_rounded:,.4f}"
        d_rounded = money.money(d)
        return f"{d_rounded:,.2f}"
    except (InvalidOperation, ValueError, TypeError):
        return str(value)


@app.template_filter("fmt_price")
def fmt_price_filter(value):
    """Format a price value with 4 decimal places and thousands separators."""
    return fmt_money_filter(value, dp=4)


@app.template_filter("fmt_int")
def fmt_int_filter(value):
    """Format an integer (e.g. share quantity) with thousands separators."""
    if value is None or value == "":
        return "—"
    try:
        val_int = int(str(value).strip().replace(",", ""))
        return f"{val_int:,}"
    except (ValueError, TypeError):
        return str(value)


@app.template_filter("fmt_rate")
def fmt_rate_filter(value):
    """Format a rate or percentage with one decimal place per DESIGN.md."""
    if value is None or value == "":
        return "N/A"
    try:
        val_str = str(value).strip().replace("%", "")
        d = Decimal(val_str)
        return f"{d:.1f}%"
    except (InvalidOperation, ValueError, TypeError):
        return f"{value}%"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/stocks")
def stocks():
    stock_list = []
    for info in universe.get_universe():
        sym = info["symbol"]
        recent_bars = list(db.price_bars.find({"symbol": sym}).sort("date", -1).limit(2))
        if recent_bars:
            latest = prices._doc_to_bar(recent_bars[0])
            latest_close = latest["close"]
            last_date = latest["date"].strftime("%Y-%m-%d")
            if len(recent_bars) > 1:
                prev = prices._doc_to_bar(recent_bars[1])
                prev_close = prev["close"]
                change = latest_close - prev_close
                change_pct = (change / prev_close) * Decimal(100) if prev_close else Decimal(0)
            else:
                change = Decimal(0)
                change_pct = Decimal(0)

            stock_list.append({
                "symbol": sym,
                "name": info["name"],
                "sector": info["sector"],
                "exchange": info["exchange"],
                "currency": info["currency"],
                "has_data": True,
                "last_close": money.price(latest_close),
                "last_date": last_date,
                "change": money.price(change),
                "change_pct": f"{change_pct:+.2f}%",
                "is_pos": change > 0,
                "is_neg": change < 0,
            })
        else:
            stock_list.append({
                "symbol": sym,
                "name": info["name"],
                "sector": info["sector"],
                "exchange": info["exchange"],
                "currency": info["currency"],
                "has_data": False,
                "last_close": None,
                "last_date": None,
                "change": None,
                "change_pct": None,
                "is_pos": False,
                "is_neg": False,
            })
    return render_template("stocks/index.html", stocks=stock_list)


@app.route("/stocks/<symbol>")
def stock_detail(symbol):
    clean_symbol = symbol.strip().upper()
    info = universe.get_symbol_info(clean_symbol)
    if not info:
        abort(404)

    recent_bars = list(db.price_bars.find({"symbol": clean_symbol}).sort("date", -1).limit(2))
    if recent_bars:
        latest = prices._doc_to_bar(recent_bars[0])
        latest_close = latest["close"]
        last_date = latest["date"].strftime("%Y-%m-%d")
        if len(recent_bars) > 1:
            prev = prices._doc_to_bar(recent_bars[1])
            prev_close = prev["close"]
            change = latest_close - prev_close
            change_pct = (change / prev_close) * Decimal(100) if prev_close else Decimal(0)
        else:
            change = Decimal(0)
            change_pct = Decimal(0)

        quote = {
            "has_data": True,
            "last_close": money.price(latest_close),
            "last_date": last_date,
            "change": money.price(change),
            "change_pct": f"{change_pct:+.2f}%",
            "is_pos": change > 0,
            "is_neg": change < 0,
        }
    else:
        quote = {
            "has_data": False,
            "last_close": None,
            "last_date": None,
            "change": None,
            "change_pct": None,
            "is_pos": False,
            "is_neg": False,
        }

    return render_template(
        "stocks/show.html",
        symbol=clean_symbol,
        info=info,
        quote=quote,
        is_demo=universe.is_demo_symbol(clean_symbol),
    )


@app.route("/api/stocks/<symbol>/bars")
def stock_bars_api(symbol):
    clean_symbol = symbol.strip().upper()
    info = universe.get_symbol_info(clean_symbol)
    if not info:
        abort(404)

    bars = prices.get_bars(db, clean_symbol)
    if not bars:
        return jsonify({"symbol": clean_symbol, "bars": []})

    closes = [b["close"] for b in bars]
    sma20_vals = indicators.sma(closes, 20)
    sma50_vals = indicators.sma(closes, 50)
    rsi_vals = indicators.rsi(closes, 14)
    macd_line, macd_signal, macd_hist = indicators.macd(closes)

    bar_list = []
    for i, b in enumerate(bars):
        s20 = money.to_json(money.price(sma20_vals[i])) if sma20_vals[i] is not None else None
        s50 = money.to_json(money.price(sma50_vals[i])) if sma50_vals[i] is not None else None
        rsi = money.to_json(money.price(rsi_vals[i])) if rsi_vals[i] is not None else None
        m_line = money.to_json(money.price(macd_line[i])) if macd_line[i] is not None else None
        m_sig = (
            money.to_json(money.price(macd_signal[i])) if macd_signal[i] is not None else None
        )
        m_hist = money.to_json(money.price(macd_hist[i])) if macd_hist[i] is not None else None

        bar_list.append({
            "time": b["date"].strftime("%Y-%m-%d"),
            "open": money.to_json(money.price(b["open"])),
            "high": money.to_json(money.price(b["high"])),
            "low": money.to_json(money.price(b["low"])),
            "close": money.to_json(money.price(b["close"])),
            "volume": b["volume"],
            "sma20": s20,
            "sma50": s50,
            "rsi": rsi,
            "macd": m_line,
            "macd_signal": m_sig,
            "macd_hist": m_hist,
        })

    return jsonify({"symbol": clean_symbol, "bars": bar_list})


ALLOWED_SCREENER_PARAMS = {
    "sector",
    "rsi_lt",
    "rsi_gt",
    "above_sma200",
    "macd_cross_up",
    "sort",
    "dir",
}

VALID_SORT_FIELDS = {
    "symbol",
    "name",
    "sector",
    "exchange",
    "currency",
    "last_close",
    "change",
    "change_pct",
    "rsi",
    "sma50",
    "sma200",
    "avg_volume_20",
    "as_of_date",
}


@app.route("/screener")
def screener():
    all_sectors = sorted({
        info["sector"] for info in universe.get_universe() if info.get("sector")
    })

    # Validate unexpected query parameters
    unknown_params = [k for k in request.args if k not in ALLOWED_SCREENER_PARAMS]
    for param in unknown_params:
        flash(f"Unrecognized filter '{param}' was ignored.", "warning")

    filters = {}
    form_values = {
        "sector": "",
        "rsi_lt": "",
        "rsi_gt": "",
        "above_sma200": False,
        "macd_cross_up": False,
    }

    # Sector filter
    sector_raw = request.args.get("sector", "").strip()
    if sector_raw and sector_raw.lower() != "all":
        if sector_raw in all_sectors:
            filters["sector"] = sector_raw
            form_values["sector"] = sector_raw
        else:
            flash(f"Unknown sector '{sector_raw}' was ignored.", "warning")

    # RSI below filter
    rsi_lt_raw = request.args.get("rsi_lt", "").strip()
    if rsi_lt_raw:
        try:
            val_lt = money.parse_decimal(rsi_lt_raw)
            if Decimal(0) <= val_lt <= Decimal(100):
                filters["rsi_lt"] = val_lt
                form_values["rsi_lt"] = str(val_lt)
            else:
                flash(
                    f"RSI below '{rsi_lt_raw}' must be between 0 and 100.",
                    "warning",
                )
        except (ValueError, TypeError, InvalidOperation):
            flash(f"Invalid RSI below value '{rsi_lt_raw}'.", "warning")

    # RSI above filter
    rsi_gt_raw = request.args.get("rsi_gt", "").strip()
    if rsi_gt_raw:
        try:
            val_gt = money.parse_decimal(rsi_gt_raw)
            if Decimal(0) <= val_gt <= Decimal(100):
                filters["rsi_gt"] = val_gt
                form_values["rsi_gt"] = str(val_gt)
            else:
                flash(
                    f"RSI above '{rsi_gt_raw}' must be between 0 and 100.",
                    "warning",
                )
        except (ValueError, TypeError, InvalidOperation):
            flash(f"Invalid RSI above value '{rsi_gt_raw}'.", "warning")

    # Check for inverted RSI range
    if (
        filters.get("rsi_lt") is not None
        and filters.get("rsi_gt") is not None
        and filters["rsi_gt"] >= filters["rsi_lt"]
    ):
        msg = (
            f"RSI above ({filters['rsi_gt']}) is greater than or equal to "
            f"RSI below ({filters['rsi_lt']})."
        )
        flash(msg, "info")

    # Above SMA200 filter
    above_sma200_raw = request.args.get("above_sma200", "").strip()
    if above_sma200_raw:
        if above_sma200_raw.lower() in ("1", "true", "on", "yes"):
            filters["above_sma200"] = True
            form_values["above_sma200"] = True
        elif above_sma200_raw.lower() in ("0", "false", "off", "no"):
            form_values["above_sma200"] = False
        else:
            flash(
                f"Invalid value '{above_sma200_raw}' for above SMA200 filter.",
                "warning",
            )

    # MACD cross up filter
    macd_cross_up_raw = request.args.get("macd_cross_up", "").strip()
    if macd_cross_up_raw:
        if macd_cross_up_raw.lower() in ("1", "true", "on", "yes"):
            filters["macd_cross_up"] = True
            form_values["macd_cross_up"] = True
        elif macd_cross_up_raw.lower() in ("0", "false", "off", "no"):
            form_values["macd_cross_up"] = False
        else:
            flash(
                f"Invalid value '{macd_cross_up_raw}' for MACD cross up filter.",
                "warning",
            )

    # Sort and direction validation
    sort_raw = request.args.get("sort", "symbol").strip()
    dir_raw = request.args.get("dir", "asc").strip().lower()

    clean_sort_field = sort_raw
    clean_dir = dir_raw
    if sort_raw.startswith("-"):
        clean_sort_field = sort_raw[1:]
        clean_dir = "desc"
    elif sort_raw.endswith("_desc"):
        clean_sort_field = sort_raw[:-5]
        clean_dir = "desc"
    elif sort_raw.endswith("_asc"):
        clean_sort_field = sort_raw[:-4]
        clean_dir = "asc"

    if clean_sort_field not in VALID_SORT_FIELDS:
        flash(f"Invalid sort parameter '{sort_raw}'. Showing default order.", "warning")
        clean_sort_field = "symbol"
        clean_dir = "asc"

    if clean_dir not in ("asc", "desc"):
        flash(f"Invalid sort direction '{dir_raw}'. Defaulted to ascending.", "warning")
        clean_dir = "asc"

    stocks = screener_module.run_screen(
        db,
        filters=filters,
        sort=clean_sort_field,
        direction=clean_dir,
    )
    as_of_date = screener_module.get_latest_as_of_date(db)
    as_of_str = as_of_date.strftime("%Y-%m-%d") if as_of_date else None

    return render_template(
        "screener.html",
        stocks=stocks,
        sectors=all_sectors,
        form_values=form_values,
        current_sort=clean_sort_field,
        current_dir=clean_dir,
        as_of_date=as_of_str,
    )


@app.route("/api/fees")
def fees_api():
    symbol = request.args.get("symbol", "").strip().upper()
    side = request.args.get("side", "buy").strip().lower()
    qty_str = request.args.get("qty", "").strip()
    price_str = request.args.get("price", "").strip()
    currency = request.args.get("currency", "").strip().upper()

    if not symbol and not currency:
        return jsonify({"error": "Symbol or currency is required."}), 400

    if symbol:
        info = universe.get_symbol_info(symbol)
        if info:
            currency = info["currency"]
        elif not currency:
            currency = "MYR"
    elif not currency:
        currency = "MYR"

    if side not in ("buy", "sell"):
        return jsonify({"error": "Side must be buy or sell."}), 400

    try:
        qty = int(qty_str)
        if qty <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Quantity must be a positive integer."}), 400

    try:
        p = money.parse_decimal(price_str)
        if p <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Price must be positive."}), 400

    if currency == "USD":
        flat_fee_str = request.args.get("flat_fee", "0.00").strip()
        flat_fee = money.parse_decimal(flat_fee_str) if flat_fee_str else Decimal("0.00")
        est = fees.estimate_us_fees(qty, p, flat_fee)
        return jsonify({
            "currency": "USD",
            "fees": money.to_json(est),
            "breakdown": {"total": money.to_json(est)},
        })

    est = fees.estimate_bursa_fees(side, qty, p)
    return jsonify({
        "currency": "MYR",
        "fees": money.to_json(est["total"]),
        "breakdown": {
            "brokerage": money.to_json(est["brokerage"]),
            "clearing": money.to_json(est["clearing"]),
            "stamp_duty": money.to_json(est["stamp_duty"]),
            "sst": money.to_json(est["sst"]),
            "total": money.to_json(est["total"]),
        },
    })


@app.route("/portfolios")
@login_required
def portfolios_list():
    user_id = current_user.get_id()
    user_portfolios = portfolios.list_portfolios(db, user_id)
    return render_template("portfolios/index.html", portfolios=user_portfolios)


@app.route("/portfolios/new", methods=["GET", "POST"])
@login_required
def portfolio_create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        currency = request.form.get("currency", "MYR").strip().upper()
        user_id = current_user.get_id()
        try:
            p_id = portfolios.create_portfolio(db, user_id, name, currency)
            return redirect(url_for("portfolio_detail", portfolio_id=str(p_id)))
        except ValueError as err:
            flash(str(err), "danger")
    return render_template("portfolios/new.html")


@app.route("/demo")
def demo():
    demo_user = users.get_by_email(db, DEMO_USER_EMAIL)
    if not demo_user:
        abort(404)
    portfolio = db.portfolios.find_one({
        "user_id": demo_user["_id"],
        "name": "Bursa journal",
    })
    if not portfolio:
        portfolio = db.portfolios.find_one({"user_id": demo_user["_id"]})
    if not portfolio:
        abort(404)

    data = trades.get_portfolio_dashboard_data(db, portfolio)
    return render_template(
        "portfolios/show.html",
        **data,
        read_only=True,
        is_demo=True,
    )


@app.route("/demo/calendar")
def demo_calendar():
    demo_user = users.get_by_email(db, DEMO_USER_EMAIL)
    if not demo_user:
        abort(404)
    portfolio = db.portfolios.find_one({
        "user_id": demo_user["_id"],
        "name": "Bursa journal",
    })
    if not portfolio:
        portfolio = db.portfolios.find_one({"user_id": demo_user["_id"]})
    if not portfolio:
        abort(404)

    today = datetime.now(timezone.utc)
    try:
        year = int(request.args.get("year", today.year))
        month = int(request.args.get("month", today.month))
        weeks = journal_calendar.month_grid(year, month)
    except (ValueError, OverflowError):
        abort(400, description="Choose a valid calendar year and month.")
    recorded = [trades._doc_to_trade(doc) for doc in trades.list_trades(db, portfolio["_id"])]
    _, realized = fifo_positions(recorded)
    totals = journal_calendar.daily_pnl(realized, year, month)
    return render_template(
        "portfolios/calendar.html",
        portfolio=portfolio,
        weeks=weeks,
        totals=totals,
        year=year,
        month=month,
        month_label=datetime(year, month, 1).strftime("%B %Y"),
        read_only=True,
        is_demo=True,
    )


@app.route("/portfolios/<portfolio_id>")
@login_required
def portfolio_detail(portfolio_id):
    user_id = current_user.get_id()
    portfolio = portfolios.get_portfolio(db, portfolio_id, user_id=user_id)
    if not portfolio:
        abort(404)

    data = trades.get_portfolio_dashboard_data(db, portfolio)
    return render_template("portfolios/show.html", **data)


@app.route("/portfolios/<portfolio_id>/import", methods=["GET", "POST"])
@login_required
def portfolio_import(portfolio_id):
    user_id = current_user.get_id()
    portfolio = portfolios.get_portfolio(db, portfolio_id, user_id=user_id)
    if not portfolio:
        abort(404)
    rows, errors, preview_id, note = [], [], None, None
    if request.method == "POST":
        source = request.form.get("format", "csv")
        upload = request.files.get("file")
        if source not in ("csv", "pdf"):
            errors = ["Choose CSV or synthetic contract note PDF."]
        elif not upload or not upload.filename:
            errors = ["Choose a PDF file." if source == "pdf" else "Choose a CSV file."]
        else:
            limit = pdf_import.MAX_BYTES if source == "pdf" else csv_import.MAX_BYTES
            contents = upload.stream.read(limit + 1)
            if len(contents) > limit:
                abort(413, description=f"{source.upper()} file exceeds the upload size limit.")
            try:
                if source == "pdf":
                    rows, note = pdf_import.parse_contract_note(contents)
                else:
                    rows, errors = csv_import.parse_trades_csv(contents.decode("utf-8-sig"))
            except UnicodeDecodeError:
                errors = ["CSV files must use UTF-8 text."]
            except ValueError as error:
                errors = [str(error)]
            if not errors:
                try:
                    preview_id = imports.create_preview(
                        db, user_id, portfolio_id, rows, source,
                        requires_acknowledgement=bool(note and note["requires_acknowledgement"]),
                    )
                except portfolios.PortfolioNotFoundError:
                    abort(404)
                except ValueError as error:
                    errors = [str(error)]
    return render_template(
        "portfolios/import.html", portfolio=portfolio, rows=rows,
        errors=errors, preview_id=preview_id, note=note,
    ), 400 if errors else 200


@app.route("/imports/<preview_id>/confirm", methods=["POST"])
@login_required
def import_confirm(preview_id):
    try:
        preview = imports.confirm_preview(
            db, current_user.get_id(), preview_id,
            acknowledge_mismatch=request.form.get("acknowledge_mismatch") == "on",
        )
    except (imports.PreviewNotFoundError, portfolios.PortfolioNotFoundError):
        abort(404)
    except portfolios.StaleVersionError as error:
        abort(409, description=str(error))
    except (ValueError, TypeError) as error:
        abort(400, description=str(error))
    except PyMongoError:
        abort(503, description="Import could not be saved. Please upload it again.")
    if preview["status"] == "failed":
        abort(409, description="This import failed. Please upload it again.")
    flash(
        "Import confirmed." if preview["status"] == "confirmed" else "Import is being confirmed.",
        "success" if preview["status"] == "confirmed" else "info",
    )
    return redirect(url_for("portfolio_detail", portfolio_id=str(preview["portfolio_id"])))


@app.route("/portfolios/<portfolio_id>/calendar")
@login_required
def portfolio_calendar(portfolio_id):
    portfolio = portfolios.get_portfolio(db, portfolio_id, user_id=current_user.get_id())
    if not portfolio:
        abort(404)
    today = datetime.now(timezone.utc)
    try:
        year = int(request.args.get("year", today.year))
        month = int(request.args.get("month", today.month))
        weeks = journal_calendar.month_grid(year, month)
    except (ValueError, OverflowError):
        abort(400, description="Choose a valid calendar year and month.")
    recorded = [trades._doc_to_trade(doc) for doc in trades.list_trades(db, portfolio["_id"])]
    _, realized = fifo_positions(recorded)
    totals = journal_calendar.daily_pnl(realized, year, month)
    return render_template(
        "portfolios/calendar.html", portfolio=portfolio, weeks=weeks, totals=totals,
        year=year, month=month, month_label=datetime(year, month, 1).strftime("%B %Y"),
    )


@app.route("/portfolios/<portfolio_id>/trades/new", methods=["GET", "POST"])
@login_required
def trade_add(portfolio_id):
    user_id = current_user.get_id()
    portfolio = portfolios.get_portfolio(db, portfolio_id, user_id=user_id)
    if not portfolio:
        abort(404)

    if request.method == "POST":
        symbol = request.form.get("symbol", "").strip().upper()
        side = request.form.get("side", "buy").strip().lower()
        qty = request.form.get("qty", "").strip()
        price_val = request.form.get("price", "").strip()
        fees_val = request.form.get("fees", "0.00").strip()
        trade_date = request.form.get("date", "").strip()
        version_val = request.form.get("version", "").strip()

        try:
            trades.add_trade(
                db,
                user_id=user_id,
                portfolio_id=portfolio["_id"],
                symbol=symbol,
                side=side,
                qty=qty,
                price_val=price_val,
                fees_val=fees_val,
                trade_date=trade_date,
                expected_version=version_val,
            )
            flash("Trade added successfully.", "success")
            return redirect(url_for("portfolio_detail", portfolio_id=portfolio_id))
        except portfolios.StaleVersionError as err:
            abort(409, description=str(err))
        except portfolios.PortfolioNotFoundError:
            abort(404)
        except (ValueError, TypeError) as err:
            flash(str(err), "danger")
            portfolio = portfolios.get_portfolio(db, portfolio_id, user_id=user_id)

    return render_template(
        "portfolios/trade_form.html",
        portfolio=portfolio,
        trade=None,
        action="add",
    )


@app.route("/portfolios/<portfolio_id>/trades/<trade_id>/edit", methods=["GET", "POST"])
@login_required
def trade_edit(portfolio_id, trade_id):
    user_id = current_user.get_id()
    portfolio = portfolios.get_portfolio(db, portfolio_id, user_id=user_id)
    if not portfolio:
        abort(404)

    trade_doc = trades.get_trade(db, trade_id, portfolio_id=portfolio["_id"])
    if not trade_doc:
        abort(404)

    if request.method == "POST":
        symbol = request.form.get("symbol", "").strip().upper()
        side = request.form.get("side", "buy").strip().lower()
        qty = request.form.get("qty", "").strip()
        price_val = request.form.get("price", "").strip()
        fees_val = request.form.get("fees", "0.00").strip()
        trade_date = request.form.get("date", "").strip()
        version_val = request.form.get("version", "").strip()

        try:
            trades.edit_trade(
                db,
                user_id=user_id,
                portfolio_id=portfolio["_id"],
                trade_id=trade_doc["_id"],
                symbol=symbol,
                side=side,
                qty=qty,
                price_val=price_val,
                fees_val=fees_val,
                trade_date=trade_date,
                expected_version=version_val,
            )
            flash("Trade updated successfully.", "success")
            return redirect(url_for("portfolio_detail", portfolio_id=portfolio_id))
        except portfolios.StaleVersionError as err:
            abort(409, description=str(err))
        except portfolios.PortfolioNotFoundError:
            abort(404)
        except (ValueError, TypeError) as err:
            flash(str(err), "danger")
            portfolio = portfolios.get_portfolio(db, portfolio_id, user_id=user_id)

    d_tz = (
        trade_doc["date"]
        if trade_doc["date"].tzinfo
        else trade_doc["date"].replace(tzinfo=timezone.utc)
    )
    trade_data = {
        "_id": str(trade_doc["_id"]),
        "symbol": trade_doc["symbol"],
        "side": trade_doc["side"],
        "qty": trade_doc["qty"],
        "price": str(money.from_d128(trade_doc["price"])),
        "fees": str(money.from_d128(trade_doc["fees"])),
        "date": d_tz.strftime("%Y-%m-%d"),
    }
    return render_template(
        "portfolios/trade_form.html",
        portfolio=portfolio,
        trade=trade_data,
        action="edit",
    )


@app.route("/portfolios/<portfolio_id>/trades/<trade_id>/delete", methods=["POST"])
@login_required
def trade_delete(portfolio_id, trade_id):
    user_id = current_user.get_id()
    portfolio = portfolios.get_portfolio(db, portfolio_id, user_id=user_id)
    if not portfolio:
        abort(404)

    trade_doc = trades.get_trade(db, trade_id, portfolio_id=portfolio["_id"])
    if not trade_doc:
        abort(404)

    version_val = request.form.get("version", "").strip()
    try:
        trades.delete_trade(
            db,
            user_id=user_id,
            portfolio_id=portfolio["_id"],
            trade_id=trade_doc["_id"],
            expected_version=version_val,
        )
        flash("Trade deleted.", "success")
    except portfolios.StaleVersionError as err:
        abort(409, description=str(err))
    except portfolios.PortfolioNotFoundError:
        abort(404)
    except (ValueError, TypeError) as err:
        flash(str(err), "danger")

    return redirect(url_for("portfolio_detail", portfolio_id=portfolio_id))


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        try:
            users.create_user(db, email, password)
        except ValueError as error:
            flash(str(error), "danger")
        except DuplicateKeyError:
            flash("That email is already registered.", "danger")
        else:
            login_user(User(users.get_by_email(db, email)))
            return redirect(url_for("index"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        doc = users.get_by_email(db, request.form.get("email", ""))
        if users.verify_password(doc, request.form.get("password", "")):
            login_user(User(doc))
            return redirect(safe_next(request.args.get("next")) or url_for("index"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/account")
@login_required
def account():
    return render_template("account.html")


@app.route("/learn")
def learn():
    all_lessons = lessons.list_lessons()
    completed_slugs = (
        progress.progress(db, current_user.get_id())
        if current_user.is_authenticated
        else set()
    )
    return render_template(
        "learn/index.html",
        lessons=all_lessons,
        completed_slugs=completed_slugs,
    )


@app.route("/learn/<slug>")
def lesson_detail(slug):
    lesson = lessons.get_lesson(slug)
    if not lesson:
        abort(404)
    all_lessons = lessons.list_lessons()
    completed_slugs = (
        progress.progress(db, current_user.get_id())
        if current_user.is_authenticated
        else set()
    )
    is_completed = slug in completed_slugs

    prev_lesson = None
    next_lesson = None
    for idx, item in enumerate(all_lessons):
        if item["slug"] == slug:
            if idx > 0:
                prev_lesson = all_lessons[idx - 1]
            if idx + 1 < len(all_lessons):
                next_lesson = all_lessons[idx + 1]
            break

    return render_template(
        "learn/show.html",
        lesson=lesson,
        is_completed=is_completed,
        total_lessons=len(all_lessons),
        prev_lesson=prev_lesson,
        next_lesson=next_lesson,
    )


@app.route("/learn/<slug>/complete", methods=["POST"])
@login_required
def lesson_complete(slug):
    lesson = lessons.get_lesson(slug)
    if not lesson:
        abort(404)
    progress.mark_complete(db, current_user.get_id(), slug)
    flash(f"Completed '{lesson['title']}'!", "success")
    return redirect(url_for("lesson_detail", slug=slug))


@app.route("/health")
def health():
    return jsonify({"status": "ok", "env": APP_ENV})


@app.route("/robots.txt")
def robots_txt():
    body = (
        "\n".join(
            [
                "User-agent: *",
                "Allow: /",
                "Sitemap: " + SITE_URL + "/sitemap.xml",
            ]
        )
        + "\n"
    )
    return Response(body, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    # Minimal static sitemap. For dynamic, DB-driven sitemaps use the add-capability skill (seo).
    urls = [
        SITE_URL + url_for("index"),
        SITE_URL + url_for("stocks"),
        SITE_URL + url_for("demo"),
        SITE_URL + url_for("screener"),
        SITE_URL + url_for("learn"),
    ]
    for item in lessons.list_lessons():
        urls.append(SITE_URL + url_for("lesson_detail", slug=item["slug"]))
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{u}</loc></url>" for u in urls)
        + "</urlset>"
    )
    return Response(body, mimetype="application/xml")


if __name__ == "__main__":
    if IS_PRODUCTION:
        # Production: proper WSGI server. The native Flask server is dev-only.
        serve(app, host="0.0.0.0", port=PORT)
    else:
        # development / testing: native Flask server with the debugger.
        app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
