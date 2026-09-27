import httpx
import pytest

from mcp_bybit.bybit import BybitClient
from mcp_bybit.errors import SymbolNotFound, TooManyCandles
from mcp_bybit.tools.history import get_price_history

from .fake_bybit import FixtureTransport


def make_client(transport=None) -> BybitClient:
    return BybitClient(transport=transport or FixtureTransport())


async def test_daily_candles_for_a_short_period():
    client = make_client()
    result = await get_price_history(client, "BTCUSDT", "2024-01-01", "2024-01-10", "1d")

    assert result.symbol == "BTCUSDT"
    assert result.price_unit == "USDT"
    assert result.summary is not None
    assert result.summary.candles_count == 10
    assert [c.begin for c in result.candles] == sorted(c.begin for c in result.candles)
    await client.aclose()


async def test_long_period_is_truncated_to_300_candles_but_summary_covers_all():
    client = make_client()
    result = await get_price_history(client, "BTCUSDT", "2024-01-01", "2024-01-04", "15m")

    assert result.summary is not None
    assert result.summary.candles_count == 384  # 4 дня * 96 пятнадцатиминуток
    assert result.candles_returned == 300
    assert len(result.candles) == 300
    assert result.candles_truncated is True
    await client.aclose()


async def test_pagination_across_multiple_kline_calls():
    client = make_client()
    result = await get_price_history(client, "BTCUSDT", "2024-01-01", "2024-01-11", "15m")

    assert result.summary is not None
    assert result.summary.candles_count == 1056  # 11 дней * 96 пятнадцатиминуток, требует 2 страницы Bybit
    assert result.candles_truncated is True
    assert result.candles_returned == 300
    await client.aclose()


async def test_too_large_period_is_rejected_without_network_call():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("не должно быть обращения к бирже")

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(TooManyCandles):
        await get_price_history(client, "BTCUSDT", "2024-01-01", "2024-03-01", "15m")
    await client.aclose()


async def test_unknown_symbol_is_error_naming_it():
    client = make_client()
    with pytest.raises(SymbolNotFound, match="NOPEUSDT"):
        await get_price_history(client, "NOPEUSDT", "2024-01-01", "2024-01-02", "1d")
    await client.aclose()


async def test_price_unit_for_non_standard_quote_coin():
    client = make_client()
    result = await get_price_history(client, "ETHBTC", "2024-01-01", "2024-01-03", "1d")

    assert result.quote_coin == "BTC"
    assert result.price_unit == "BTC"
    await client.aclose()
