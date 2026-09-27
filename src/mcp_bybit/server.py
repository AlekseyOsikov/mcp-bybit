"""Точка входа MCP-сервера: регистрация инструментов, транспорты, запуск."""

import argparse
import logging
import sys
import time
from collections.abc import Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .bybit import BybitClient
from .errors import BybitError
from .models import (
    BenchmarkComparison,
    BenchmarkHistoryParam,
    DateFromParam,
    DateTillParam,
    HistoryAParam,
    HistoryBParam,
    HistoryParam,
    HistoryResult,
    IntervalParam,
    LimitParam,
    MetricsResult,
    PairComparison,
    PriceResult,
    QueryParam,
    SearchSymbolsResult,
    SymbolParam,
)
from .tools import analytics, history, price, search

SERVER_NAME = "mcp-bybit"
LOOPBACK_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8000

INSTRUCTIONS = (
    "Спотовые рыночные данные Bybit (публичный v5 API, без ключей): поиск пар, текущая цена, история цен. "
    "Порядок работы: если известна только монета, а не точный тикер, найдите его через search_symbols; затем "
    "get_current_price для цены и get_price_history для истории. Чтобы посчитать метрики или сравнить пары, "
    "передайте результаты get_price_history без изменений в compute_price_metrics, compare_with_benchmark "
    "(с эталоном, например BTCUSDT) или compare_securities (две пары). Работает только со спотовым рынком; "
    "деривативы (linear, inverse, option) и приватные эндпоинты не поддерживаются."
)

READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=True)
"""Инструменты чтения только читают публичные данные биржи."""

ANALYTICS = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
"""Инструменты анализа считают по переданной истории и не обращаются ни к бирже, ни к файлам."""

_T = TypeVar("_T")


async def _guard(call: Awaitable[_T]) -> _T:
    """Доменную ошибку отдаём агенту её текстом; непредвиденные сбои SDK превращает в общую ошибку без деталей."""
    try:
        return await call
    except BybitError as error:
        raise ToolError(str(error)) from error


def create_server(client: BybitClient | None = None, clock: Callable[[], float] | None = None) -> MCPServer:
    """Собирает сервер. Без `client` использует настоящий клиент Bybit и закрывает его при остановке.

    `clock` (секунды Unix) нужен тестам: им пользуется признак незавершённой свечи в анализе.
    """
    bybit_client = client if client is not None else BybitClient()
    owns_client = client is None
    now = clock or time.time

    def today() -> date:
        """Сегодняшняя дата UTC."""
        return datetime.fromtimestamp(now(), UTC).date()

    @asynccontextmanager
    async def lifespan(_: MCPServer):
        try:
            yield None
        finally:
            if owns_client:
                await bybit_client.aclose()

    server = MCPServer(SERVER_NAME, instructions=INSTRUCTIONS, lifespan=lifespan)

    @server.tool(name="search_symbols", description=search.DESCRIPTION, annotations=READ_ONLY)
    async def search_symbols(query: QueryParam, limit: LimitParam = 10) -> SearchSymbolsResult:
        return await _guard(search.search_symbols(bybit_client, query, limit))

    @server.tool(name="get_current_price", description=price.DESCRIPTION, annotations=READ_ONLY)
    async def get_current_price(symbol: SymbolParam) -> PriceResult:
        return await _guard(price.get_current_price(bybit_client, symbol))

    @server.tool(name="get_price_history", description=history.DESCRIPTION, annotations=READ_ONLY)
    async def get_price_history(
        symbol: SymbolParam,
        date_from: DateFromParam,
        date_till: DateTillParam = None,
        interval: IntervalParam = "1d",
    ) -> HistoryResult:
        return await _guard(history.get_price_history(bybit_client, symbol, date_from, date_till, interval))

    @server.tool(name="compute_price_metrics", description=analytics.METRICS_DESCRIPTION, annotations=ANALYTICS)
    async def compute_price_metrics(history: HistoryParam) -> MetricsResult:
        return await _guard(analytics.compute_price_metrics(history, today()))

    @server.tool(name="compare_with_benchmark", description=analytics.BENCHMARK_DESCRIPTION, annotations=ANALYTICS)
    async def compare_with_benchmark(
        history: HistoryParam, benchmark_history: BenchmarkHistoryParam
    ) -> BenchmarkComparison:
        return await _guard(analytics.compare_with_benchmark(history, benchmark_history, today()))

    @server.tool(name="compare_securities", description=analytics.SECURITIES_DESCRIPTION, annotations=ANALYTICS)
    async def compare_securities(history_a: HistoryAParam, history_b: HistoryBParam) -> PairComparison:
        return await _guard(analytics.compare_securities(history_a, history_b, today()))

    return server


def configure_logging() -> None:
    """Журнал только в stderr: по stdio в stdout идёт протокол, любой посторонний вывод его ломает."""
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # иначе каждый запрос к Bybit попадает в журнал


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-bybit",
        description="MCP-сервер спотовых рыночных данных Bybit (v5 API). По умолчанию работает по stdio.",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="stdio (по умолчанию: клиент сам запускает сервер) или streamable-http на 127.0.0.1",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_HTTP_PORT,
        help=f"порт для streamable-http (по умолчанию {DEFAULT_HTTP_PORT}); адрес всегда {LOOPBACK_HOST}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    configure_logging()
    server = create_server()
    run_kwargs: dict[str, Any] = {}
    if args.transport == "streamable-http":
        run_kwargs = {"host": LOOPBACK_HOST, "port": args.port}
        logger = logging.getLogger(__name__)
        logger.info("Streamable HTTP на http://%s:%d/mcp", LOOPBACK_HOST, args.port)
    server.run(args.transport, **run_kwargs)


if __name__ == "__main__":
    main()
