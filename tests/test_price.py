import pytest

from mcp_bybit.bybit import BybitClient
from mcp_bybit.errors import SymbolNotFound, SymbolNotTrading
from mcp_bybit.tools.price import get_current_price

from .fake_bybit import FixtureTransport, MutatingTransport, set_result_field


def make_client(transport) -> BybitClient:
    return BybitClient(transport=transport)


async def test_get_current_price_for_spot_pair():
    client = make_client(FixtureTransport())
    result = await get_current_price(client, "BTCUSDT")

    assert result.symbol == "BTCUSDT"
    assert result.base_coin == "BTC"
    assert result.quote_coin == "USDT"
    assert result.price_unit == "USDT"
    assert result.price > 0
    assert result.trading_status == "Trading"
    await client.aclose()


async def test_lowercase_symbol_resolves_to_canonical():
    client = make_client(FixtureTransport())
    result = await get_current_price(client, "btcusdt")

    assert result.symbol == "BTCUSDT"
    await client.aclose()


async def test_unknown_symbol_is_error_naming_it():
    client = make_client(FixtureTransport())
    with pytest.raises(SymbolNotFound, match="NOPEUSDT"):
        await get_current_price(client, "NOPEUSDT")
    await client.aclose()


async def test_non_trading_pair_is_error_with_status():
    def mutate(path: str, payload: dict) -> None:
        if path.endswith("instruments-info"):
            set_result_field(payload, "status", "Delisted", row=0)

    client = make_client(MutatingTransport(mutate))
    with pytest.raises(SymbolNotTrading, match="Delisted"):
        await get_current_price(client, "BTCUSDT")
    await client.aclose()
