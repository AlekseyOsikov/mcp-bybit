"""Резолвер `symbol` -> инструмент по спотовому справочнику Bybit (`instruments-info`)."""

from dataclasses import dataclass

from .bybit import REFERENCE_TTL, BybitClient
from .errors import SymbolNotFound, UnsupportedCategory

SPOT = "spot"
_OTHER_CATEGORIES = ("linear", "inverse")
"""Категории, которые проверяются только для более точного сообщения об ошибке (см. UnsupportedCategory)."""


@dataclass(frozen=True)
class Instrument:
    symbol: str
    base_coin: str
    quote_coin: str
    status: str


def _to_instrument(row: dict) -> Instrument:
    return Instrument(
        symbol=row["symbol"],
        base_coin=row["baseCoin"],
        quote_coin=row["quoteCoin"],
        status=row["status"],
    )


async def resolve(client: BybitClient, symbol: str) -> Instrument:
    """Находит спотовую пару по тикеру (регистр не важен).

    Raises:
        SymbolNotFound: пары с таким тикером нет ни в одной категории Bybit.
        UnsupportedCategory: тикер существует, но только среди деривативов (linear/inverse).
    """
    canonical = symbol.strip().upper()
    result = await client.get_result(
        "v5/market/instruments-info",
        {"category": SPOT, "symbol": canonical},
        ttl=REFERENCE_TTL,
    )
    rows = result.get("list", []) if isinstance(result, dict) else []
    if rows:
        return _to_instrument(rows[0])

    for category in _OTHER_CATEGORIES:
        other = await client.get_result(
            "v5/market/instruments-info",
            {"category": category, "symbol": canonical},
            ttl=REFERENCE_TTL,
        )
        other_rows = other.get("list", []) if isinstance(other, dict) else []
        if other_rows:
            raise UnsupportedCategory(canonical, category)

    raise SymbolNotFound(canonical)


async def list_spot_instruments(client: BybitClient) -> list[Instrument]:
    """Полный справочник спотовых пар Bybit, кэшируется отдельно от точечного резолвинга."""
    result = await client.get_result(
        "v5/market/instruments-info",
        {"category": SPOT},
        ttl=REFERENCE_TTL,
    )
    rows = result.get("list", []) if isinstance(result, dict) else []
    return [_to_instrument(row) for row in rows]
