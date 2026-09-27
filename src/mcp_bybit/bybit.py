"""Тонкий async-клиент Bybit v5: GET, повторы, кэш в памяти, разбор конверта retCode/retMsg/result."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

from .errors import BybitUnavailable, SymbolNotFound

logger = logging.getLogger(__name__)

BASE_URL = "https://api.bybit.com"

QUOTE_TTL = 5.0
"""Кэш тикеров, секунды: у крипты нет задержки биржи, короткий TTL просто гасит всплеск одинаковых вызовов."""

REFERENCE_TTL = 6 * 60 * 60.0
"""Кэш справочника инструментов (instruments-info), секунды: состав торгуемых пар меняется редко."""

_MAX_CACHE_ENTRIES = 512

_PARAM_ERROR_CODE = 10001
"""retCode Bybit для ошибок параметров запроса; конкретная причина различается только текстом `retMsg`."""


class BybitClient:
    """Общий async-клиент Bybit v5 с повторами на сбоях и кэшем ответов."""

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
        retries: int = 2,
        backoff: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url,
            transport=transport,
            timeout=timeout,
            headers={"User-Agent": "mcp-bybit/0.1"},
            follow_redirects=True,
            # Bybit публичен и доступен напрямую. Прокси из окружения httpx не всегда умеет разобрать,
            # и клиент падал бы ещё при создании.
            trust_env=False,
        )
        self._retries = retries
        self._backoff = backoff
        self._clock = clock
        self._sleep = sleep
        self._cache: dict[tuple[str, tuple[tuple[str, str], ...]], tuple[float, tuple[Any, int]]] = {}

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_result(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        ttl: float = 0.0,
    ) -> Any:
        """GET `path` (например `v5/market/tickers`), содержимое `result` ответа.

        При `ttl > 0` ответ кэшируется в памяти на `ttl` секунд. Возвращаемые данные нельзя менять.
        """
        result, _ = await self.get_result_with_time(path, params, ttl=ttl)
        return result

    async def get_result_with_time(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        ttl: float = 0.0,
    ) -> tuple[Any, int]:
        """Как `get_result`, но также возвращает `time` конверта ответа (мс, время сервера Bybit)."""
        query = dict(params or {})
        key = (path, tuple(sorted((name, str(value)) for name, value in query.items())))

        if ttl > 0:
            cached = self._cache.get(key)
            if cached is not None and cached[0] > self._clock():
                return cached[1]

        entry = await self._fetch(path, query)

        if ttl > 0:
            self._store(key, entry, ttl)
        return entry

    def _store(self, key: tuple[str, tuple[tuple[str, str], ...]], entry: tuple[Any, int], ttl: float) -> None:
        if len(self._cache) >= _MAX_CACHE_ENTRIES:
            now = self._clock()
            self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
            while len(self._cache) >= _MAX_CACHE_ENTRIES:
                self._cache.pop(next(iter(self._cache)))
        self._cache[key] = (self._clock() + ttl, entry)

    async def _fetch(self, path: str, query: Mapping[str, Any]) -> tuple[Any, int]:
        failure = ""
        for attempt in range(self._retries + 1):
            if attempt:
                logger.warning("Bybit %s: повтор %d/%d после сбоя: %s", path, attempt, self._retries, failure)
                await self._sleep(self._backoff * attempt)
            try:
                response = await self._http.get(path, params=query)
            except httpx.TransportError as exc:
                failure = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
                continue

            status = response.status_code
            if status == 429 or status >= 500:
                failure = f"HTTP {status}"
                continue
            if not response.is_success:
                raise BybitUnavailable(f"HTTP {status} на {path}")
            try:
                payload = response.json()
            except ValueError as exc:
                raise BybitUnavailable(f"ответ {path} не является JSON") from exc
            if not isinstance(payload, Mapping):
                raise BybitUnavailable(f"неожиданный формат ответа {path}")

            return self._unwrap(path, query, payload)

        raise BybitUnavailable(f"{path}: {failure}")

    def _unwrap(self, path: str, query: Mapping[str, Any], payload: Mapping[str, Any]) -> tuple[Any, int]:
        ret_code = payload.get("retCode")
        if ret_code == 0:
            return payload.get("result"), payload.get("time", 0)
        ret_msg = payload.get("retMsg") or ""
        symbol = query.get("symbol")
        if ret_code == _PARAM_ERROR_CODE and symbol and "symbol" in ret_msg.lower():
            raise SymbolNotFound(str(symbol))
        detail = f"retCode {ret_code}: {ret_msg}" if ret_msg else f"retCode {ret_code}"
        raise BybitUnavailable(detail)
