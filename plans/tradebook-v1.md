# Plan: tradebook v1

## Goal

Build a public portfolio repository that shows Python web development (Flask 3, PyMongo, Bootstrap 5, vanilla JS) and stock-market domain knowledge. It ships as seven independently shippable phases. Phases A to C are the first useful release; D to G follow without blocking it.

## Hard rules (every phase, every worker)

1. **Clean room.** Write all code from scratch. Workers must not read, open, search, copy, or paraphrase any other project on this machine. The only allowed outside file is the house-style auth recipe named in A3. No data, URLs, product names, company names, database names, or API endpoints from the author's past or current employers, and no comments or docs that mention them. The private denylist is supplied in each worker brief, never in the repo. Every phase review checks this first.
2. **No personal paths or secrets.** No absolute home-directory paths, personal emails, tokens, or real broker statements in any committed file. `.env` stays gitignored.
3. **Market data.** Live prices come from `yfinance`, for local personal use only. Tests, the offline demo, and any hosted demo use deterministic synthetic data generated in code. Never commit downloaded data.
4. **House style** per `CLAUDE.md`: functional modules taking `db` explicitly, thin routes, imports at top, no classes except framework-required ones (`User(UserMixin)`), custom exceptions, or `frozen=True` dataclasses.
5. **Money policy** (see `sources/money.py`, Phase B):
   - Python side: `Decimal` only for prices, quantities in money math, fees, cash, P/L, game balances.
   - Mongo side: every persisted money field is `Decimal128` on write and `.to_decimal()` on read, converted only in `sources/money.py` helpers.
   - JSON side: money and prices are decimal strings. JavaScript converts to `Number` only for chart rendering.
   - Provider floats convert once at ingestion via `Decimal(str(x))`. Reject NaN and Infinity at every boundary.
   - Prices keep 4 decimal places; money rounds to 2 places with `ROUND_HALF_UP`. Dates are stored as UTC midnight `datetime` for the exchange-local trading day.
6. **UI is Bootstrap 5 only** (CDN, 5.3.x) with Jinja2 and vanilla JS, including the game. Customize through CSS variables in `static/css/theme.css`. No Tailwind, React, jQuery, or other CSS frameworks. Use the `frontend-bootstrap-evolution` skill so it does not look like stock Bootstrap.
7. **Tests make no external HTTP calls.** Real MongoDB integration tests are allowed and expected.

## Scope

- In scope: the seven phases below, tests, CI, Docker Compose, README.
- Out of scope: creating the GitHub repo, pushing, deploying (main session does these with user approval), payments, email, i18n, FX conversion, short selling, corporate actions (splits are flagged as unsupported), real broker PDF layouts, offline CSS/JS assets (CDN is required).

## Approach

Phases run in order. Milestones marked *(parallel)* do not depend on each other.

### Phase A: Scaffold, provenance, quality baseline

#### Milestone A1: Provenance and hygiene
1. `sources/errors.py`: delete and rewrite from scratch (one `error.html` template for every HTTP status, JSON for XHR/API callers). The generated version carries a provenance comment pointing at employer code; do not read that version while rewriting. Review every other generated file for comments that name an origin and rewrite those too.
2. `CLAUDE.md`, `README.md`: switch to uv. Replace the absolute venv path and every `pip`/`python` command with `uv sync` and `uv run ...` (uv manages `.venv/`). Keep every other `CLAUDE.md` rule.
3. `pyproject.toml`: `[project]` with `requires-python = ">=3.12"` and dependencies moved from `requirements.txt` plus `Flask-Login>=0.6`, `Flask-WTF>=1.2`, `Flask-Limiter>=3.5`; `[dependency-groups] dev = ["pytest>=8", "ruff>=0.6"]`; `[tool.ruff]` (line length 100, target py312, select `E,F,W,I,B`); `[tool.uv] package = false`. Delete `requirements.txt`. Run `uv lock` and commit-ready `uv.lock`. Add `.python-version` with `3.12`.
4. Fix whatever ruff flags in the scaffold.
5. `LICENSE`: MIT, "Mohamad Khairulamirin". `.gitignore`: add `.pytest_cache/`, `.ruff_cache/`.
6. `sources/config.py`: in production, raise at startup if `SECRET_KEY` is missing or equals a known placeholder (`dev-secret-change-me`, `change-me-in-production`). Add `COOKIE_SECURE` (default true in production) so local HTTP Compose can set it false.
→ Verify: `uv sync` succeeds; `uv run ruff check .` passes; `APP_ENV=production SECRET_KEY=change-me-in-production uv run python tradebook.py` exits with a clear error.

#### Milestone A2: Test harness and clean-room guard
1. `tests/conftest.py`, set before any app import: `APP_ENV=testing`, `MONGO_URI` from `TEST_MONGO_URI` (default `mongodb://localhost:27017`), `DB_NAME=tradebook_test`. Fixture `db` asserts the connected database name ends in `_test` before cleaning, deletes all documents from every collection (keeps the database), then calls `ensure_indexes(db)`. Fixture `client` depends on `db`, sets `WTF_CSRF_ENABLED=False` and `RATELIMIT_ENABLED=False`. Fixture `logged_in_client` registers and logs in a fresh user.
2. `tests/test_health.py::test_health_ok`: GET `/health` returns 200 and `status == "ok"` (the scaffold also returns `env`; keep it).
3. `tests/test_clean_room.py`:
   - Candidates are `git ls-files --cached --others --exclude-standard`, so it works before the first commit. Fail if the list is empty.
   - Denylist is stored as SHA-256 hashes of lowercase tokens, so the repo never contains the plaintext. The main session supplies the hashes in the brief.
   - Tokenize each text file (split on non-alphanumerics, also check hyphen and underscore joins) and fail on any hash match.
   - Also fail on the regex `/(Users|home)/[a-z]` and on any email address other than an allowlist (`noreply@anthropic.com`, `user@example.com`).
   - Self-test: write a temp file with a constructed banned token and with a clean control, assert the scanner flags only the first.
→ Verify: `uv run pytest -q` passes against local `mongod`; temporarily adding a home path to a file makes the guard fail.

#### Milestone A3: Auth
1. Follow `~/Projects/coding-agent-skills/skills/add-capability/capabilities/auth.md` (the author's own recipe, allowed). Change: logout is POST with a CSRF token; GET `/logout` returns 405.
2. `tests/test_auth.py`: register; duplicate email rejected (proves the unique index survives the fixture reset); wrong password rejected; `@login_required` redirects.
3. `tests/test_security.py` with CSRF enabled: register/login/logout POST without token returns 400. With rate limiting enabled and fresh limiter storage: the 6th login POST in a minute returns 429.
→ Verify: tests pass; manual register, login, logout in the browser.

#### Milestone A4: Containers and CI *(parallel with A3)*
1. `Dockerfile`: single stage `python:3.12-slim`, copy the uv binary from `ghcr.io/astral-sh/uv` (pinned tag), `uv sync --frozen --no-dev`, non-root user, `CMD ["uv", "run", "--no-sync", "python", "tradebook.py"]`.
2. `docker-compose.yml`: `mongo` (`mongo:7`, named volume, port `27017:27017` for local tests, healthcheck with `mongosh --eval "db.adminCommand('ping')"`). `web` (build `.`, port 5000, `env_file: .env`, then `environment:` overrides `MONGO_URI=mongodb://mongo:27017`, `APP_ENV=production`, `COOKIE_SECURE=false`; `depends_on: mongo: condition: service_healthy`).
3. `.github/workflows/ci.yml`: push and pull_request; `astral-sh/setup-uv` (pinned major); `services: mongo:7` on 27017; `uv sync --frozen`; `uv run ruff check .`; `uv run pytest -q`. CI running green is the workflow's validation.
→ Verify: `docker compose up --build`, then register and log in at `http://localhost:5000` and reload a logged-in page.

**Gate after Phase A:** Bootstrap 5 design pass with the user (`prototype-ui`), producing `DESIGN.md` and `design/<feature>/DECISIONS.md`. Phases B to G build to it.

### Phase B: Market data and stock page

#### Milestone B1: Money helpers and indicators
1. `sources/money.py`: `to_d128(value)`, `from_d128(value)`, `parse_decimal(text)` (rejects NaN/Infinity/empty), `money(d)` (2 dp), `price(d)` (4 dp), `to_json(d)` (string). Tests in `tests/test_money.py` including a real Mongo round trip.
2. `modules/indicators.py`: `sma`, `ema`, `rsi` (Wilder, n=14), `macd` (12, 26, 9). Inputs and outputs are lists of `Decimal`, `None` for warm-up. Document the flat-series RSI case.
3. `tests/test_indicators.py`: hand-computed cases, warm-up counts, RSI within 0..100.
→ Verify: `pytest tests/test_money.py tests/test_indicators.py -v`.

#### Milestone B2: Price store, synthetic data, provider adapter *(parallel with B1 after `sources/money.py`)*
1. `modules/synthetic.py`: `generate_ohlcv(symbol, start, sessions, seed)`, GBM with `random.Random(seed)`, weekdays only, deterministic.
2. `modules/prices.py`: `ensure_indexes`, `upsert_bars`, `get_bars`, `latest_bar`. Collection `price_bars`, unique index `(symbol, date)`.
3. `modules/market_source.py` (only file importing `yfinance`): `fetch_daily(symbol)` calls `yfinance.download(symbol, period="2y", interval="1d", auto_adjust=True, multi_level_index=False, progress=False, timeout=20)`. Bars are split/dividend adjusted; say so in the UI. Normalize dates to the exchange-local day, drop rows with any non-finite OHLCV, return `[]` on empty or failure. Never raise into callers.
4. `sources/universe.py`: about 30 tickers (Bursa `.KL` and US large caps) with name, sector, exchange, currency (`MYR` or `USD`). Plus 5 `DEMO*` symbols (currency `MYR`).
5. `scripts/refresh_prices.py`, run as `uv run python -m scripts.refresh_prices`: `--demo` seeds 320 sessions per demo symbol (enough for SMA200 and crossovers); default fetches the universe and keeps last-good bars when a fetch returns nothing. Prints per-symbol counts and failures.
6. `tests/test_market_source.py`: replace `yfinance.download` with synthetic DataFrames (normal, empty, NaN row, raised exception). `tests/test_prices.py`: idempotent upsert, deterministic synthetic data.
→ Verify: `uv run python -m scripts.refresh_prices --demo`, then `mongosh tradebook --eval 'db.price_bars.countDocuments()'` is 1600.

#### Milestone B3: Stock page
1. Routes: `GET /stocks` (universe with last close, day change, last bar date, "no data" state), `GET /stocks/<symbol>`, `GET /api/stocks/<symbol>/bars` (decimal strings, plus SMA20, SMA50, RSI, MACD).
2. `templates/stocks/index.html`, `templates/stocks/show.html`, `static/js/stock_chart.js` with TradingView Lightweight Charts from CDN at one pinned version. Use that version's API for panes. Show the library's NOTICE attribution text and TradingView link on chart pages.
3. `tests/test_stock_routes.py`: unknown symbol 404, seeded symbol JSON shape, prices are strings.
→ Verify: open `/stocks/DEMO1` and see candles, SMA overlay, RSI and MACD panes, attribution visible.

### Phase C: Trading journal

#### Shared contracts (write first, in `modules/ledger.py` docstring and tests)
- Portfolio: `user_id`, `name`, `currency` (`MYR` or `USD`), `version` (int). Single currency. Trades in a different currency than the portfolio are rejected.
- Trade: `portfolio_id`, `symbol` (uppercase, from universe or free text), `side` (`buy`/`sell`), `qty` (positive integer shares), `price` (Decimal128), `fees` (Decimal128, actual fees as entered or imported, authoritative), `date`, `seq` (integer order within the date, assigned on insert), `source` (`manual`/`csv`/`pdf`), `import_id` (optional).
- Long only. A sell that exceeds open quantity for that symbol is invalid.
- FIFO order is `(date, seq)` per symbol. Buy fees are allocated to lots by quantity; when a lot is partly closed, its remaining fee share stays with the open remainder. Rounding remainder goes to the last allocation so fees are conserved exactly.
- A "trade" in statistics is one closed lot portion. Break-even (P/L == 0) is neither win nor loss. Profit factor is `None` when there are no losses.
- Every write (add, edit, delete, import confirm) replays the full proposed history of each affected symbol through `fifo_positions`, and saves only if it is valid.
- Concurrency: writes first claim the portfolio with `update_one({_id, user_id, version: v}, {$inc: {version: 1}})`. If 0 documents match, return 409. Shortcut: optimistic lock on the portfolio document, fine for one host; a crash between the claim and the trade write only bumps the version.

#### Milestone C1: Ledger math (pure)
1. `modules/pnl.py`: `fifo_positions(trades)` returns open lots and realized lot portions (entry, exit, qty, P/L after allocated fees, holding days). `summary(realized)` returns total P/L, win rate, average win, average loss, profit factor, largest win and loss.
2. `modules/fees.py`: `estimate_bursa_fees(side, qty, price, brokerage_rate, min_brokerage)` for ordinary listed shares only, using the dated schedule in `sources/fee_schedule.py`. It holds the effective date, source URLs, and values, which the main session verifies and supplies before C1 starts. Ballpark at planning time: stamp duty RM1 per RM1,000 or fraction, capped RM1,000; clearing 0.03% capped RM1,000; SST treatment to be verified. Estimates only prefill the form; stored fees are what the user confirms. `estimate_us_fees` is a flat configurable educational estimate.
3. `tests/test_pnl.py`: same-day ordering via `seq`, interleaved symbols, partial closes conserve fees, oversized sell raises `ValueError`, zero trades give `None` win rate, no losses give `None` profit factor. `tests/test_fees.py`: each RM1,000 threshold, minimum brokerage, both caps.
→ Verify: `pytest tests/test_pnl.py tests/test_fees.py -v`.

#### Milestone C2: Portfolios and trades
1. `modules/portfolios.py`, `modules/trades.py`: CRUD scoped by `user_id`, using the shared contracts. Indexes: `portfolios (user_id)`, `trades (portfolio_id, symbol, date, seq)`.
2. Routes and templates: `/portfolios`, `/portfolios/<id>` (open positions with unrealized P/L from the latest bar and its date, or "no price" when missing; realized table; summary cards in the portfolio currency), trade form with fee estimate from `/api/fees`.
3. `tests/test_portfolios.py`: cross-user read and write return 404; editing an old buy that would make a later sell invalid is rejected and nothing changes; currency mismatch rejected; stale version returns 409.
→ Verify: tests pass; create a portfolio and trades in the browser.

#### Milestone C3: Calendar and CSV import (parsers parallel with C2; routes after C2)
1. `modules/calendar.py`: `daily_pnl(realized, year, month)`. Route `/portfolios/<id>/calendar`, month grid colored by realized P/L.
2. `modules/csv_import.py`: `parse_trades_csv(text)` with columns `date,symbol,side,qty,price,fees`. Returns `(rows, errors)` with line numbers. Max 1 MB, 5,000 rows.
3. `modules/imports.py` (shared by C3 and E): `create_preview(db, user_id, portfolio_id, rows, source)` stores rows in `import_previews` (TTL index, 1 hour; status `pending`). `confirm_preview(db, user_id, preview_id)`:
   - Rechecks ownership and currency, and replays the full proposed history.
   - Flips status `pending`→`confirming` with a conditional update, so a double submit does nothing.
   - `insert_many` with a shared `import_id`. On failure, deletes by `import_id` and sets status `failed`. On success sets `confirmed`.
   - The client only sends the preview id. The parsed rows never go in the session cookie or logs.
4. `tests/test_csv_import.py`: valid file, bad date, negative qty, unknown side, double confirm inserts once, other user's preview id returns 404, an invalid history at confirm time is rejected.
→ Verify: import `tests/fixtures/sample_trades.csv` through the UI.

#### Demo seed
`uv run python -m scripts.seed_demo` creates `demo@example.com` with a MYR portfolio of about 20 trades on `DEMO*` symbols, so a fresh checkout has a populated journal. Requires `--demo` prices first.

#### Public read-only demo
- `GET /demo` (no login) renders the seeded demo portfolio with the same dashboard template as `/portfolios/<id>`, in read-only mode: no forms, no add/edit/delete/import controls, and a visible "Synthetic demo data, read-only" banner.
- The route looks up the demo user by a config value `DEMO_USER_EMAIL` (default `demo@example.com`). It returns 404 when that user or portfolio does not exist.
- Every write route keeps its ownership check, so the demo account cannot be modified through `/demo`. The demo account has no usable password: the seed sets an unusable hash, so nobody can log in as it.
- Tests (`tests/test_demo.py`): `/demo` is 200 without login and shows no form or CSRF token; POSTs to any portfolio or trade route for the demo portfolio from an anonymous or other user are rejected; a login attempt as the demo email fails.

### Phase D: Screener

1. `modules/screener.py`: `build_snapshot(db)` stores one document per symbol in `screener_snapshot`: last close, change %, SMA50, SMA200, RSI14, `macd_cross_up` (histogram turned positive on the last bar), 20-day average volume, sector, as-of date.
2. `run_screen(db, filters, sort)`: filters `rsi_lt`, `rsi_gt`, `above_sma200`, `macd_cross_up`, `sector`, built as one Mongo query. Indexes only on `sector` and `rsi` to start.
3. `scripts/refresh_prices.py` calls `build_snapshot` at the end.
4. Route `/screener`: GET-param filter form (shareable URL), sortable table, as-of date shown.
5. `tests/test_screener.py`: snapshot from synthetic data, each filter, combined filters.
→ Verify: `/screener?rsi_lt=30` returns only rows with RSI under 30.

### Phase E: Synthetic contract-note PDF import

Demonstrates PDF parsing on a fictional contract-note layout designed for this project. It does not claim support for any real broker.

1. `tests/fixtures/make_contract_note.py`: generate PDFs with `reportlab` at test time (contract number, trade and settlement dates, stock code and name, side, qty, price, brokerage, clearing fee, stamp duty, tax, net amount). No PDFs committed.
2. `modules/pdf_import.py`: `parse_contract_note(pdf_bytes)` with `pdfplumber`. Limits are 5 MB, `%PDF-` magic bytes, at most 10 pages, and 200 KB extracted text. Encrypted, image-only, or malformed files get a clear error. Reconciliation rule: buy net = gross + fees, sell net = gross − fees, within RM0.01. A mismatch blocks confirm until the user ticks an acknowledgement.
3. Upload route feeds `modules/imports.create_preview`. The upload is never written to disk.
4. `tests/test_pdf_import.py`: buy, sell, mismatch blocks confirm, non-PDF rejected, 11-page file rejected, encrypted file rejected.
→ Verify: upload a generated fixture in the UI and confirm it.

### Phase F: Lessons

1. `content/lessons/*.md`: 8 original lessons with YAML front matter (`slug`, `title`, `order`, `related_filters`): candlesticks, moving averages, RSI, MACD, position sizing, FIFO and realized P/L, Bursa trading costs (cites the dated fee schedule), keeping a journal. Each ends with a "try it" link into the app.
2. `modules/lessons.py`: load at startup with `markdown` and `PyYAML`; `list_lessons()`, `get_lesson(slug)`. `modules/progress.py`: `mark_complete`, `progress`. Collection `lesson_progress`, unique `(user_id, slug)`.
3. Routes `/learn`, `/learn/<slug>`, POST `/learn/<slug>/complete` (login required, CSRF). Guests can read.
4. Screener filter labels and journal summary cards link to the matching lesson.
5. `tests/test_lessons.py`: front matter parsed, unknown slug 404, completing twice stays one record.
→ Verify: complete a lesson and see progress update on `/learn`.

### Phase G: Stock-market tycoon game

Original design.

1. `modules/game_engine.py` (pure):
   - `new_game(seed)`: day 1 of 30, own cash RM10,000, plus a RM10,000 margin loan already credited (cash RM20,000, principal RM10,000), interest 0.5% per day on outstanding principal, accrued at each `next_day` including the move into day 30. Six fictional companies in different sectors with precomputed GBM paths. News events from `random.Random(seed * 1000 + day)` shock one sector.
   - `apply_action(state, action)`: `buy`, `sell`, `repay`, `next_day`. Quantity must be a positive integer; repay must be positive and at most min(cash, debt). Invalid actions raise `GameError`.
   - Score at end = cash + holdings marked at the day-30 close − outstanding principal − unpaid interest, rounded to 2 dp. Starting score is RM10,000.
   - `public_view(state)` returns only the current day, visible history up to today, holdings, cash, debt, news so far. Never future prices or the seed.
2. `modules/games.py`: game documents carry `owner` (`user:<id>` or `guest:<random token>` held in the signed session), `version`, `state`, and on completion `score`, `nickname`, `finished_at`. Actions use `update_one({_id, owner, version: v}, {$set: ..., $inc: {version: 1}})`; 0 matched returns 409. Leaderboard is a query on finished games, top 20 by score, index `(finished_at exists, score desc)`.
3. Routes: `/play` (guest allowed, nickname 3 to 20 chars, profanity not handled in v1), `/play/<game_id>` (owner only, else 404), POST `/api/play/<game_id>/action` (owner only, CSRF token in header, rate limited, returns `public_view`), `/play/leaderboard`.
4. `templates/play/*.html`, `static/js/game.js` (vanilla JS, Bootstrap 5): market board, holdings, cash and loan, news ticker, day counter, end screen.
5. Tests:
   - `tests/test_game_engine.py`: same seed gives same game; cannot buy beyond cash; cannot sell unheld; interest accrues; zero-trade score reconciles to RM10,000 minus 29 days of interest; game rejects actions after day 30.
   - `tests/test_games.py`: other guest session and other user get 404 on read and action; stale version gets 409; retrying the final action does not change the score; response JSON has no future prices.
→ Verify: play a full game in the browser and see it on the leaderboard.

## UI / Design

- Prototype: required, after Phase A. New product with no `DESIGN.md`.
- Design questions: (1) visual direction for a finance tool recruiters judge in 10 seconds; (2) portfolio dashboard layout; (3) game screen layout.
- All UI is Bootstrap 5.

## Schema / Data Changes

Collections: `users`, `price_bars`, `portfolios`, `trades`, `import_previews`, `screener_snapshot`, `lesson_progress`, `games`. Each module has `ensure_indexes(db)`; `tradebook.py` calls them all at startup and tests call them after each reset. No migrations.

## Acceptance Criteria

- [ ] `ruff check .` and `pytest -q` pass locally and in GitHub Actions after every phase.
- [ ] `docker compose up --build` on an empty database, then `uv run python -m scripts.refresh_prices --demo` and `uv run python -m scripts.seed_demo`, gives a working app with no market-data provider calls (CDN assets still needed).
- [ ] `tests/test_clean_room.py` passes and its self-test proves it can fail. A manual review of the public tree before the first push finds no employer references or secrets.
- [ ] No test makes external HTTP calls.
- [ ] Money crosses Mongo only through `sources/money.py`; tests assert `Decimal` types on read and string types in JSON.
- [ ] Users and guests cannot read or change another owner's portfolio, trades, import previews, or games.
- [ ] README has a screenshot per feature, an architecture section, setup in under 5 commands, the Yahoo personal-use note, and an "educational, not financial advice" disclaimer.

## Tests

- Unit tests for pure modules; Flask test-client integration tests against a real MongoDB `tradebook_test` database.
- Run: `uv run pytest -q` with local `mongod` or `docker compose up mongo`.

## Rollback

New repository, additive phases. Revert a phase with `git revert`.

## Dependencies

- Managed with uv in `pyproject.toml`. Runtime: Flask, pymongo, python-dotenv, waitress, Flask-Login, Flask-WTF, Flask-Limiter (A); yfinance, pandas via yfinance (B); markdown, PyYAML (F); pdfplumber (E).
- Dev: pytest, ruff, reportlab (E fixtures only).
- CDN: Bootstrap 5.3, Bootstrap Icons, Lightweight Charts (pinned).

## Review log

- 2026-11-11, Codex design critique (three Bootstrap 5 directions, recommends A). User chose an A vs B prototype and a public read-only demo.
- 2026-11-11, user: switch dependency management to uv (pyproject.toml, uv.lock, `uv run`), applied to A1, A4 and all commands.
- 2026-11-11, Codex plan review (15 findings: 1 critical, 12 major, 2 minor). All accepted and folded in above.
  - Clean-room guard design: hashed denylist, untracked files included, self-test.
  - `errors.py` rewrite.
  - Test DB safety and index rebuild after each reset.
  - Compose networking and cookies; placeholder-secret rejection.
  - Single-currency portfolios.
  - Ledger, FIFO and concurrency contract.
  - Money policy beyond bars.
  - Dated fee schedule with actual fees authoritative.
  - Yahoo adapter tests, explicit arguments and personal-use scope.
  - Import preview and confirm contract; Phase E renamed to synthetic.
  - Game ownership, public view, versioned updates and score definition.
  - Rate-limit and CSRF test strategy; POST logout.
  - Offline redefined, demo seed added.
  - Health contract, `python -m` scripts, Mongo port, PyYAML timing.
  - Chart NOTICE text.
  - Simplifications: single-stage Dockerfile, no one-entry parser registry, indexes only for real queries.

## Decisions Log

| Decision | Chosen | Alternatives Considered | Why |
|----------|--------|------------------------|-----|
| v1 scope | All: journal, stock pages, screener, PDF import, lessons, game | Journal + stock pages; screener first; journal + screener; include PDF import | User asked for all; phased so each ships alone |
| Framework | Flask | Bottle; Flask + small FastAPI API | User choice; common in job ads, matches house style |
| Market data | yfinance (local use) plus synthetic seed | Seed only; Stooq CSV | User choice. Synthetic for tests and hosted demo; Yahoo data is for personal use |
| Repo name | tradebook | bursa-trade-journal; pnl-desk | User choice |
| Phase order | A to G as listed | Game right after market data | User choice; game reuses earlier code |
| Builder | Plan, then agy/pi swarm | Main session directly; plan only | User choice |
| Code provenance | Clean-room rewrite, hashed-denylist guard in CI | Copy and clean old code; plaintext denylist | Old code belongs to employers and other contributors; plaintext list would itself leak names |
| UI framework | Bootstrap 5 only, themed via CSS variables | Tailwind; React | User requirement |
| Environment and deps | uv (`pyproject.toml`, `uv.lock`, `uv run`) | Repo-local venv + requirements.txt; house-style absolute venv | User decision 2026-11-11: every project uses uv. No personal paths; reproducible lockfile |
| Test database | Real MongoDB, clear collections and rebuild indexes per test | mongomock; drop database | Real driver behaviour; keeps unique indexes under test |
| Portfolio currency | Single currency per portfolio | Multi-currency with FX | Correct totals without FX scope |
| Concurrency | Optimistic version on portfolio and game documents | Transactions (need replica set); no locking | Works on standalone Mongo, simple |
| Fees | User-confirmed actual fees stored; estimator prefills | Always computed | Rates change; historical trades must keep real fees |
| PDF import | One fictional layout, labelled synthetic | Real broker layout | No real statements or third-party layouts in a public repo |
| Charts | Lightweight Charts with NOTICE text | Chart.js; proprietary Charting Library | Candles out of the box; license allows it with attribution |
| Game guests | Guest play with random owner token | Login required | Recruiters will not register to try a demo |
| Leaderboard | Query finished games | Separate collection | One write, no divergence |
| Offline | No provider calls; CDN required | Vendor all assets | Keeps the Bootstrap CDN rule |
| Prototype | Required after Phase A | Skip | No DESIGN.md; first impression matters |
| Recruiter access | Public read-only `/demo` of the seeded portfolio | Game only for guests | User choice 2026-11-11; strongest first 10 seconds without exposing real data |
| Design comparison | Prototype A (Exchange ledger) vs B (Open journal) from Codex critique | A only; A vs C; all three | User choice |
