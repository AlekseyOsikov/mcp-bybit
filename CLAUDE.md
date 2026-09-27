# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An MCP server exposing Bybit's public v5 REST API (spot market only, no API keys, no trading/account endpoints) as six read-only tools for an LLM agent: `search_symbols`, `get_current_price`, `get_price_history`, `compute_price_metrics`, `compare_with_benchmark`, `compare_securities`. It is modeled directly on a sibling project, `mcp-moex` (same architecture, ported from MOEX securities to Bybit spot pairs).

## Commands

```bash
uv sync                                        # install deps into .venv
uv run mcp-bybit                               # run the server (stdio transport)
uv run mcp-bybit --transport streamable-http --port 8000   # debug transport, 127.0.0.1 only

uv run pytest                                  # full test suite, no network allowed
uv run pytest tests/test_history.py -q         # a single test file
uv run pytest tests/test_history.py::test_daily_candles_for_a_short_period  # a single test
RECORD_FIXTURES=1 uv run pytest                # record missing Bybit fixtures from the live API

uv run python scripts/smoke_client.py          # end-to-end check against the real Bybit API
```

## Architecture

Layered, in dependency order — each layer only talks to the one below it:

1. **`bybit.py`** — thin async HTTP client (`BybitClient`). Unwraps Bybit's `{retCode, retMsg, result, time}` envelope, retries on 429/5xx/network errors, in-memory TTL cache. `get_result()` returns just `result`; `get_result_with_time()` also returns the envelope's `time` (used for `as_of`, since Bybit's ticker payload itself carries no per-quote timestamp). Bybit reuses `retCode 10001` for many distinct parameter errors distinguished only by `retMsg` text — `_unwrap()` pattern-matches on that text (see `_PARAM_ERROR_CODE`) rather than trusting a specific code.
2. **`resolver.py`** — resolves a `symbol` string to an `Instrument` (base/quote coin, status) via `instruments-info?category=spot`. On a miss it also probes `linear`/`inverse` before giving up, so a derivatives-only symbol gets `UnsupportedCategory` instead of a generic `SymbolNotFound`. `list_spot_instruments()` fetches the whole spot catalog for `search_symbols`, cached separately from single-symbol lookups.
3. **`tools/`** — one module per tool (`search.py`, `price.py`, `history.py`, `analytics.py`), each a thin async function taking a `BybitClient` (or, for analytics, no client at all) and returning a pydantic model from `models.py`. This is the layer to edit when Bybit's response shape or a tool's business rule changes.
4. **`analytics/`** — pure, network-free, stateless math ported from `mcp-moex`'s analytics engine and adapted for crypto:
   - `series.py` validates a client-supplied `get_price_history` result before trusting it (rejects truncated history, unsupported intervals, inconsistent summaries) — the analytics tools never call Bybit themselves, they only recompute over data the agent already fetched.
   - `stats.py` — volatility/drawdown/correlation/beta, pure functions on price sequences. Note `ANNUALIZATION_FACTORS = {"1d": 365, ...}` (not 252 like MOEX) because crypto trades every day of the year.
   - `core.py` builds `Leg`/`Aligned` structures and the note strings (fee/benchmark disclaimers, split/liquidity-jump warnings).
   - `build.py` wires validated `Series` into the three tool result shapes; this is where `IntervalMismatch` and `QuoteCoinMismatch` are enforced before two histories are compared.
   - `text.py` renders the deterministic Russian `text` summary field — no LLM involved, the numbers in `text` are guaranteed to match the structured result because they're formatted from it.
5. **`server.py`** — `create_server()` wires everything into an `MCPServer`, registers all six tools with `readOnlyHint=true`, and wraps each call in `_guard()` which turns a `BybitError` into a `ToolError` (safe to show the agent) while letting unexpected exceptions surface as generic MCP tool errors (no internal detail leaked). `main()` is the CLI entry point (`argparse`, stdio vs streamable-http).

**Scope boundary that shapes the whole codebase:** only `category = spot` is supported. There's no per-tool category parameter, no funding rate / open interest / order book, and no watch/scheduling mode (present in `mcp-moex` but explicitly out of scope here) — see `openspec/changes/add-bybit-spot-mcp-server/design.md` for why.

## Testing conventions

- Tests never touch the network by default: `tests/conftest.py` monkeypatches `socket.socket.connect` to raise. Run `RECORD_FIXTURES=1 uv run pytest` to lift that guard and let missing fixtures be recorded from the live Bybit API into `tests/fixtures/` (see `tests/fake_bybit.py`'s `FixtureTransport`).
- `tests/fake_bybit.py` also provides `MutatingTransport` (replay a fixture with one field patched, e.g. to simulate a delisted symbol) and `set_result_field()` for that purpose — useful when the live API can't currently produce the edge case you need (e.g. every spot symbol is currently `Trading`).
- `tests/analytics_helpers.py`'s `make_history()` builds synthetic `HistoryResult` objects by hand for analytics tests — those never need fixtures since analytics never calls Bybit.
- `tests/test_bybit_client.py` and `tests/test_server.py` use `httpx.MockTransport`/in-memory MCP `Client` rather than recorded fixtures, since they're testing transport-level behavior (retries, envelope parsing) or protocol-level behavior (tool registration, error surfacing), not real API responses.

## OpenSpec

This project uses OpenSpec (`openspec/`) for spec-driven planning. The current implementation was built from `openspec/changes/add-bybit-spot-mcp-server/` (proposal, per-capability spec deltas, design, tasks) — read `design.md` there for the reasoning behind interval choices, pagination, and the crypto-specific adaptations to the ported analytics engine. Use `/opsx:explore`, `/opsx:propose`, `/opsx:apply` for further changes rather than editing code ad hoc.
