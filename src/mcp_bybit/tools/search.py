"""Инструмент search_symbols: поиск спотовой пары Bybit по монете или части тикера."""

from ..bybit import BybitClient
from ..errors import InvalidArgument
from ..models import SearchSymbolsResult, SymbolHit
from ..resolver import Instrument, list_spot_instruments

DESCRIPTION = """\
Поиск спотовой пары на Bybit по коду монеты или части тикера. Возвращает тикеры (symbol), которые нужны \
инструментам get_current_price и get_price_history.

Используйте, когда пользователь назвал монету («ETH», «биткоин») или не уверен в точном написании тикера, \
а не когда тикер уже известен целиком. Ищет только спотовые пары (category = spot) со статусом Trading; \
деривативы (linear, inverse, option) не ищутся. Совпадение проверяется по подстроке в symbol, base_coin \
или quote_coin (регистр не важен). Если truncated = true, найдено больше, чем limit: уточните запрос."""


def _is_exact_match(hit: SymbolHit, query: str) -> bool:
    return hit.symbol.casefold() == query.casefold()


async def search_symbols(client: BybitClient, query: str, limit: int = 10) -> SearchSymbolsResult:
    """Находит торгуемые спотовые пары по монете или части тикера."""
    query = query.strip()
    if not query:
        raise InvalidArgument("Параметр query пуст: укажите код монеты или тикер.")

    key = query.casefold()
    instruments = await list_spot_instruments(client)
    hits = [
        SymbolHit(symbol=i.symbol, base_coin=i.base_coin, quote_coin=i.quote_coin, status=i.status)
        for i in instruments
        if i.status == "Trading" and _matches(i, key)
    ]
    hits.sort(key=lambda hit: not _is_exact_match(hit, query))  # стабильная: остальное в порядке справочника

    results = hits[:limit]
    return SearchSymbolsResult(
        query=query,
        results=results,
        count=len(results),
        truncated=len(hits) > limit,
    )


def _matches(instrument: Instrument, key: str) -> bool:
    return (
        key in instrument.symbol.casefold()
        or key in instrument.base_coin.casefold()
        or key in instrument.quote_coin.casefold()
    )
