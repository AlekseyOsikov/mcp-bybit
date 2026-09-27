"""Инструмент get_current_price: актуальная цена спотовой пары Bybit в реальном времени."""

from datetime import UTC, datetime
from typing import Any

from ..bybit import QUOTE_TTL, BybitClient
from ..errors import BybitUnavailable, SymbolNotTrading
from ..models import PriceResult
from ..resolver import resolve

DESCRIPTION = """\
Актуальная цена спотовой пары Bybit по тикеру в реальном времени: последняя цена, лучшие bid/ask, \
изменение, максимум и минимум за 24 часа, объём и оборот за 24 часа.

Единица цены (price_unit) — котируемая монета пары (например USDT для BTCUSDT, BTC для ETHBTC), она же \
quote_coin. as_of — это время формирования ответа биржей, а не индивидуальная метка последней сделки.

Если известна только монета, а не точный тикер, сначала найдите его через search_symbols. Работает только \
со спотовым рынком Bybit; деривативы (linear, inverse, option) не поддерживаются."""


def _float(value: Any) -> float:
    return float(value)


async def get_current_price(client: BybitClient, symbol: str) -> PriceResult:
    """Актуальная цена спотовой пары по её тикеру."""
    instrument = await resolve(client, symbol)
    if instrument.status != "Trading":
        raise SymbolNotTrading(instrument.symbol, instrument.status)

    result, response_time_ms = await client.get_result_with_time(
        "v5/market/tickers",
        {"category": "spot", "symbol": instrument.symbol},
        ttl=QUOTE_TTL,
    )
    rows = result.get("list", []) if isinstance(result, dict) else []
    if not rows:
        raise BybitUnavailable(f"Bybit не отдал тикер для {instrument.symbol}.")
    ticker = rows[0]

    return PriceResult(
        symbol=instrument.symbol,
        base_coin=instrument.base_coin,
        quote_coin=instrument.quote_coin,
        price=_float(ticker["lastPrice"]),
        price_unit=instrument.quote_coin,
        bid_price=_float(ticker["bid1Price"]),
        ask_price=_float(ticker["ask1Price"]),
        change_pct_24h=round(_float(ticker["price24hPcnt"]) * 100, 2),
        high_24h=_float(ticker["highPrice24h"]),
        low_24h=_float(ticker["lowPrice24h"]),
        volume_24h=_float(ticker["volume24h"]),
        turnover_24h=_float(ticker["turnover24h"]),
        as_of=datetime.fromtimestamp(response_time_ms / 1000, UTC).isoformat(),
        trading_status=instrument.status,
    )
