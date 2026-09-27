"""Инструмент get_price_history: свечи спотовой пары Bybit за период и сводка, посчитанная сервером."""

import math
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from ..bybit import QUOTE_TTL, BybitClient
from ..errors import InvalidArgument, TooManyCandles
from ..models import Candle, HistoryResult, HistorySummary, Interval
from ..resolver import resolve

BYBIT_INTERVAL: dict[Interval, str] = {"15m": "15", "1h": "60", "4h": "240", "1d": "D", "1w": "W", "1M": "M"}
"""Отображение человекочитаемого интервала на код Bybit (минуты либо D/W/M)."""

INTERVAL_MINUTES: dict[Interval, int] = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080, "1M": 40320}
"""Оценка длительности свечи в минутах (месяц взят по самому короткому — 28 дней), для отказа без сети."""

PAGE_SIZE = 1000
"""Bybit отдаёт не больше 1000 свечей за запрос."""

MAX_RETURNED_CANDLES = 300
"""Сколько последних свечей попадает в ответ; сводка считается по всем."""

MAX_CANDLES = 5000
"""Свечей за период больше этого числа — отказ до похода в сеть: слишком большой объём для обработки."""

DESCRIPTION = f"""\
История цен спотовой пары Bybit (category = spot) за период: свечи и готовая сводка.

Возвращает свечи (open, high, low, close, volume, turnover) и summary: цену начала и конца периода, \
минимум, максимум и изменение в процентах, посчитанные по ВСЕМ свечам периода. В списке candles приходят \
не более {MAX_RETURNED_CANDLES} последних свечей (см. candles_truncated). Если свечей слишком много, инструмент \
вернёт ошибку: выберите более крупный interval или сократите период. Время UTC.

Единица цен (price_unit) — котируемая монета пары (quote_coin); для пар вроде ETHBTC это не рубли и не \
доллары, а BTC.

Если известна только монета, а не точный тикер, сначала найдите его через search_symbols."""


def _parse_date(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise InvalidArgument(f"Параметр {name}: «{value}» не является датой в формате YYYY-MM-DD.") from None


def _bounds_ms(start: date, end: date) -> tuple[int, int]:
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC) - timedelta(milliseconds=1)
    return int(start_dt.timestamp() * 1000), int(end_dt.timestamp() * 1000)


def _estimate_candles(start: date, end: date, interval: Interval) -> int:
    days = (end - start).days + 1
    return math.ceil(days * 1440 / INTERVAL_MINUTES[interval])


def _to_candle(row: list[str]) -> Candle:
    start_ms, open_, high, low, close, volume, turnover = row
    begin = datetime.fromtimestamp(int(start_ms) / 1000, UTC).isoformat()
    return Candle(
        begin=begin,
        open=float(open_),
        high=float(high),
        low=float(low),
        close=float(close),
        volume=float(volume),
        turnover=float(turnover),
    )


def _summarize(candles: list[Candle]) -> HistorySummary:
    start_price = candles[0].open
    end_price = candles[-1].close
    change_abs = float(Decimal(str(end_price)) - Decimal(str(start_price)))
    return HistorySummary(
        candles_count=len(candles),
        start_price=start_price,
        end_price=end_price,
        min_price=min(candle.low for candle in candles),
        max_price=max(candle.high for candle in candles),
        change_abs=change_abs,
        change_pct=round((end_price - start_price) / start_price * 100, 2),
        first_candle=candles[0].begin,
        last_candle=candles[-1].begin,
    )


async def _fetch_rows(
    client: BybitClient, symbol: str, interval: Interval, start_ms: int, end_ms: int
) -> list[list[str]]:
    """Все строки свечей периода: страницы по `PAGE_SIZE`, сдвигая `end` назад по минимальному `startTime`."""
    rows: list[list[str]] = []
    cursor_end = end_ms
    while True:
        result = await client.get_result(
            "v5/market/kline",
            {
                "category": "spot",
                "symbol": symbol,
                "interval": BYBIT_INTERVAL[interval],
                "start": start_ms,
                "end": cursor_end,
                "limit": PAGE_SIZE,
            },
            ttl=QUOTE_TTL,
        )
        page: list[list[str]] = result.get("list", []) if isinstance(result, dict) else []
        if not page:
            break
        rows.extend(page)
        oldest_start = min(int(row[0]) for row in page)
        if len(page) < PAGE_SIZE or oldest_start <= start_ms:
            break
        cursor_end = oldest_start - 1
    return rows


async def get_price_history(
    client: BybitClient,
    symbol: str,
    date_from: str,
    date_till: str | None = None,
    interval: Interval = "1d",
) -> HistoryResult:
    """Свечи спотовой пары за период; цены в тех же единицах, что и в `get_current_price`."""
    start = _parse_date(date_from, "date_from")
    end = _parse_date(date_till, "date_till") if date_till else datetime.now(UTC).date()
    if start > end:
        raise InvalidArgument(
            f"Начало периода date_from ({start}) позже конца date_till ({end}). "
            "Поменяйте даты местами или уточните период."
        )

    if _estimate_candles(start, end, interval) > MAX_CANDLES:
        raise TooManyCandles(interval, MAX_CANDLES)

    instrument = await resolve(client, symbol)
    start_ms, end_ms = _bounds_ms(start, end)
    rows = await _fetch_rows(client, instrument.symbol, interval, start_ms, end_ms)

    candles = sorted((_to_candle(row) for row in rows), key=lambda candle: candle.begin)
    returned = candles[-MAX_RETURNED_CANDLES:]

    return HistoryResult(
        symbol=instrument.symbol,
        base_coin=instrument.base_coin,
        quote_coin=instrument.quote_coin,
        price_unit=instrument.quote_coin,
        interval=interval,
        date_from=start.isoformat(),
        date_till=end.isoformat(),
        summary=_summarize(candles) if candles else None,
        candles=returned,
        candles_returned=len(returned),
        candles_truncated=len(returned) < len(candles),
        message=None
        if candles
        else (
            f"За период с {start} по {end} нет данных: возможно, пара ещё не торговалась или период в будущем."
        ),
    )
