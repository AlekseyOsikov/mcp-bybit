import httpx
import pytest

from mcp_bybit.bybit import BybitClient
from mcp_bybit.errors import BybitUnavailable, SymbolNotFound

TICKER_PATH = "v5/market/tickers"

OK_ENVELOPE = {
    "retCode": 0,
    "retMsg": "OK",
    "result": {"category": "spot", "list": [{"symbol": "BTCUSDT", "lastPrice": "84787.1"}]},
    "retExtInfo": {},
    "time": 1790535703069,
}


async def no_sleep(_: float) -> None:
    return None


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_client(handler, **kwargs) -> BybitClient:
    kwargs.setdefault("sleep", no_sleep)
    return BybitClient(transport=httpx.MockTransport(handler), **kwargs)


# --- запрос и разбор конверта -------------------------------------------------------------------


async def test_get_result_requests_bybit_and_returns_result():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=OK_ENVELOPE)

    client = make_client(handler)
    result = await client.get_result(TICKER_PATH, {"category": "spot", "symbol": "BTCUSDT"})

    assert result["list"][0]["symbol"] == "BTCUSDT"
    request = seen[0]
    assert str(request.url).startswith(f"https://api.bybit.com/{TICKER_PATH}")
    assert request.url.params["category"] == "spot"
    await client.aclose()


async def test_ret_code_symbol_error_raises_symbol_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"retCode": 10001, "retMsg": "Not supported symbols", "result": {}})

    client = make_client(handler)
    with pytest.raises(SymbolNotFound, match="NOPEUSDT"):
        await client.get_result(TICKER_PATH, {"category": "spot", "symbol": "NOPEUSDT"})
    await client.aclose()


async def test_other_ret_code_raises_bybit_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"retCode": 10001, "retMsg": "Illegal category", "result": {}})

    client = make_client(handler)
    with pytest.raises(BybitUnavailable, match="Illegal category"):
        await client.get_result(TICKER_PATH, {"category": "spott"})
    await client.aclose()


# --- повторы и BybitUnavailable ------------------------------------------------------------------


async def test_retries_transient_failures_and_then_succeeds():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectTimeout("timeout", request=request)
        if attempts == 2:
            return httpx.Response(503)
        return httpx.Response(200, json=OK_ENVELOPE)

    client = make_client(handler, retries=2)
    result = await client.get_result(TICKER_PATH)

    assert attempts == 3
    assert result["list"][0]["symbol"] == "BTCUSDT"
    await client.aclose()


@pytest.mark.parametrize("failure", ["timeout", "503", "429"])
async def test_raises_bybit_unavailable_after_retries_are_exhausted(failure):
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if failure == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(int(failure))

    client = make_client(handler, retries=2)
    with pytest.raises(BybitUnavailable) as error:
        await client.get_result(TICKER_PATH)

    assert attempts == 3
    assert "повторите" in str(error.value).lower()
    await client.aclose()


async def test_client_error_is_not_retried():
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(404)

    client = make_client(handler, retries=2)
    with pytest.raises(BybitUnavailable, match="HTTP 404"):
        await client.get_result(TICKER_PATH)

    assert attempts == 1
    await client.aclose()


async def test_non_json_response_is_bybit_unavailable():
    client = make_client(lambda request: httpx.Response(200, text="<html>maintenance</html>"))

    with pytest.raises(BybitUnavailable, match="не является JSON"):
        await client.get_result(TICKER_PATH)
    await client.aclose()


# --- кэш ------------------------------------------------------------------------------------------


async def test_cache_serves_repeated_request_within_ttl_and_refetches_after():
    calls = 0
    clock = Clock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=OK_ENVELOPE)

    client = make_client(handler, clock=clock)

    await client.get_result(TICKER_PATH, ttl=10)
    await client.get_result(TICKER_PATH, ttl=10)
    assert calls == 1

    clock.now += 9.9
    await client.get_result(TICKER_PATH, ttl=10)
    assert calls == 1

    clock.now += 0.2
    await client.get_result(TICKER_PATH, ttl=10)
    assert calls == 2
    await client.aclose()


async def test_cache_is_keyed_by_parameters_and_disabled_without_ttl():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=OK_ENVELOPE)

    client = make_client(handler)

    await client.get_result(TICKER_PATH, {"symbol": "BTCUSDT"}, ttl=10)
    await client.get_result(TICKER_PATH, {"symbol": "ETHUSDT"}, ttl=10)
    assert calls == 2

    await client.get_result(TICKER_PATH, {"symbol": "BTCUSDT"})
    await client.get_result(TICKER_PATH, {"symbol": "BTCUSDT"})
    assert calls == 4
    await client.aclose()


async def test_failed_request_is_not_cached():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls <= 3:
            return httpx.Response(503)
        return httpx.Response(200, json=OK_ENVELOPE)

    client = make_client(handler, retries=2)
    with pytest.raises(BybitUnavailable):
        await client.get_result(TICKER_PATH, ttl=10)

    result = await client.get_result(TICKER_PATH, ttl=10)
    assert result["list"]
    await client.aclose()
