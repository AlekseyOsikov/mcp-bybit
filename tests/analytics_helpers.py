"""Фабрика историй для тестов аналитики: рукописные ряды любого интервала, без сети и фикстур."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from mcp_bybit.models import Candle, HistoryResult
from mcp_bybit.tools.history import _summarize


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def make_begins(count: int, interval: str = "1d", start: date = date(2024, 1, 5)) -> list[date]:
    if interval == "1d":
        return [start + timedelta(days=i) for i in range(count)]
    if interval == "1w":
        return [start + timedelta(weeks=i) for i in range(count)]
    if interval == "1M":
        first = start.replace(day=1)
        return [_add_months(first, i) for i in range(count)]
    raise ValueError(interval)


def iso(day: date) -> str:
    return datetime(day.year, day.month, day.day, tzinfo=UTC).isoformat()


def make_history(
    symbol: str = "BTCUSDT",
    closes: Sequence[float] = (100.0, 110.0),
    *,
    opens: Sequence[float] | None = None,
    begins: Sequence[date] | None = None,
    interval: str = "1d",
    price_unit: str = "USDT",
    start: date = date(2024, 1, 5),
    truncated: bool = False,
) -> HistoryResult:
    """История как из `get_price_history`. open первой свечи по умолчанию равен её close, дальше open = прошлый close."""
    days = list(begins) if begins is not None else make_begins(len(closes), interval, start)
    opens = list(opens) if opens is not None else [closes[0], *closes[:-1]]
    base_coin = symbol.removesuffix(price_unit) or symbol
    candles = [
        Candle(begin=iso(day), open=o, high=max(o, c), low=min(o, c), close=c, volume=1.0, turnover=float(c))
        for day, o, c in zip(days, opens, closes, strict=True)
    ]
    return HistoryResult(
        symbol=symbol,
        base_coin=base_coin,
        quote_coin=price_unit,
        price_unit=price_unit,
        interval=interval,
        date_from=days[0].isoformat(),
        date_till=days[-1].isoformat(),
        summary=_summarize(candles),
        candles=candles,
        candles_returned=len(candles),
        candles_truncated=truncated,
    )
