import httpx
import pytest

from mcp_bybit.bybit import BybitClient
from mcp_bybit.errors import InvalidArgument
from mcp_bybit.tools.search import search_symbols

from .fake_bybit import FixtureTransport, MutatingTransport, set_result_field


def make_client(transport) -> BybitClient:
    return BybitClient(transport=transport)


async def test_search_by_coin_finds_pair_with_that_base_or_quote_coin():
    client = make_client(FixtureTransport())
    result = await search_symbols(client, "eth")

    assert any(hit.symbol == "ETHUSDT" for hit in result.results)
    assert all(
        "eth" in hit.symbol.casefold() or "eth" in hit.base_coin.casefold() or "eth" in hit.quote_coin.casefold()
        for hit in result.results
    )
    await client.aclose()


async def test_search_by_full_ticker_returns_it_first():
    client = make_client(FixtureTransport())
    result = await search_symbols(client, "BTCUSDT")

    assert result.results[0].symbol == "BTCUSDT"
    await client.aclose()


async def test_empty_query_is_invalid_argument():
    client = make_client(FixtureTransport())
    with pytest.raises(InvalidArgument):
        await search_symbols(client, "   ")
    await client.aclose()


async def test_too_many_matches_are_truncated_to_limit():
    client = make_client(FixtureTransport())
    result = await search_symbols(client, "USDT", limit=3)

    assert len(result.results) == 3
    assert result.truncated is True
    assert result.count == 3
    await client.aclose()


async def test_non_trading_pair_is_excluded():
    def mutate(path: str, payload: dict) -> None:
        if path.endswith("instruments-info"):
            set_result_field(payload, "status", "Delisted", row=0)

    client = make_client(MutatingTransport(mutate))
    result = await search_symbols(client, "BTCUSDT")

    assert not any(hit.symbol == "BTCUSDT" for hit in result.results)
    await client.aclose()


async def test_derivatives_only_symbol_is_not_found_in_spot_search():
    client = make_client(FixtureTransport())
    result = await search_symbols(client, "1000BONKUSDT")

    assert result.count == 0
    await client.aclose()

