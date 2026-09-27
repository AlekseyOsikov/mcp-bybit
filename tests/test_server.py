"""Сервер целиком: клиент MCP SDK подключается к нему в памяти и вызывает инструменты."""

from mcp import Client

from mcp_bybit.bybit import BybitClient
from mcp_bybit.server import create_server

from .fake_bybit import FixtureTransport

TOOLS = {
    "search_symbols",
    "get_current_price",
    "get_price_history",
    "compute_price_metrics",
    "compare_with_benchmark",
    "compare_securities",
}


def connect(client: BybitClient | None = None) -> Client:
    """Клиент SDK, подключённый к серверу в памяти. Открывать нужно в теле теста: контекст anyio привязан к задаче."""
    return Client(create_server(client or BybitClient(transport=FixtureTransport())))


async def tools_by_name(client: Client) -> dict:
    return {tool.name: tool for tool in (await client.list_tools()).tools}


async def test_list_tools_returns_exactly_the_six_tools():
    async with connect() as client:
        assert set(await tools_by_name(client)) == TOOLS


async def test_every_tool_is_described_and_read_only():
    async with connect() as client:
        for name, tool in (await tools_by_name(client)).items():
            assert tool.description and len(tool.description) > 50, name
            assert tool.annotations is not None, name
            assert tool.annotations.read_only_hint is True, name


async def test_success_returns_structured_content_and_same_json_text():
    async with connect() as client:
        result = await client.call_tool("get_current_price", {"symbol": "BTCUSDT"})

        assert result.is_error is False
        assert result.structured_content["symbol"] == "BTCUSDT"


async def test_invalid_arguments_are_a_tool_error():
    async with connect() as client:
        result = await client.call_tool("search_symbols", {"query": "   "})
        assert result.is_error is True
        assert "query" in result.content[0].text


async def test_unknown_symbol_is_a_tool_error_naming_it():
    async with connect() as client:
        result = await client.call_tool("get_current_price", {"symbol": "NOPEUSDT"})
        assert result.is_error is True
        assert "NOPEUSDT" in result.content[0].text


async def test_unexpected_crash_is_reported_without_details(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("секретная внутренняя деталь")

    async with connect() as client:
        with monkeypatch.context() as patched:
            patched.setattr("mcp_bybit.tools.price.get_current_price", boom)
            result = await client.call_tool("get_current_price", {"symbol": "BTCUSDT"})

        assert result.is_error is True
        assert "секретная внутренняя деталь" not in result.content[0].text
        assert "Traceback" not in result.content[0].text
        # сервер жив и отвечает на следующие вызовы
        assert (await client.call_tool("get_current_price", {"symbol": "BTCUSDT"})).is_error is False
