# Tasks

## 1. Скелет проекта

- [ ] 1.1 Создать `pyproject.toml` (имя `mcp-bybit`, `requires-python >= 3.12`, зависимости `mcp`, `httpx`, `pydantic`, dev-группа `pytest`/`pytest-asyncio`, entry point `mcp-bybit = "mcp_bybit.server:main"`, `[tool.pytest.ini_options]` с `asyncio_mode = "auto"`) и проверить `uv sync` (или `pip install -e .`) без ошибок
- [ ] 1.2 Создать структуру `src/mcp_bybit/` (`__init__.py`, пустые `errors.py`, `bybit.py`, `resolver.py`, `models.py`, `server.py`, `tools/__init__.py`, `analytics/__init__.py`) и `tests/__init__.py`, `tests/fixtures/`, `scripts/` и проверить, что пакет импортируется (`python -c "import mcp_bybit"`)

## 2. HTTP-клиент Bybit и ошибки

- [ ] 2.1 Реализовать `errors.py`: базовый `BybitError` и подклассы `SymbolNotFound`, `UnsupportedCategory`, `BybitUnavailable`, `InvalidArgument`, `TooManyCandles` с человекочитаемыми русскими сообщениями
- [ ] 2.2 Реализовать `bybit.py`: async-клиент `BybitClient` (`httpx.AsyncClient(trust_env=False)`, `GET /v5/*`, разбор конверта `retCode`/`retMsg`/`result`, ретраи на `429`/`5xx`/сетевых ошибках с экспоненциальной паузой, TTL-кэш в памяти) — перенос архитектуры `iss.py` из `mcp-moex`, адаптированный под конверт Bybit
- [ ] 2.3 Настроить каркас тестов без сети: `tests/conftest.py` с фикстурой, запрещающей реальные HTTP-вызовы, и `tests/fixtures/` с записанными ответами Bybit (`instruments-info`, `tickers`, `kline`) для тикеров, используемых в тестах ниже; проверить: `pytest -k no_network` не делает сетевых обращений
- [ ] 2.4 Написать тесты `bybit.py` на ретраи (429/500 → повтор, затем успех), кэш (второй вызов в пределах TTL не бьёт по фикстуре повторно) и разбор `retCode != 0` → `BybitError`; проверить: `pytest tests/test_bybit_client.py` зелёный

## 3. Резолвер символа и поиск

- [ ] 3.1 Реализовать `resolver.py`: `resolve(client, symbol) -> Instrument(symbol, base_coin, quote_coin, status)` через `instruments-info?category=spot&symbol=...`, с TTL-кэшем (аналог `REFERENCE_TTL`), поднимает `SymbolNotFound` для отсутствующего тикера
- [ ] 3.2 Реализовать в `bybit.py`/`resolver.py` получение полного справочника spot-пар (`instruments-info?category=spot` без `symbol`) с отдельным TTL-кэшем для поиска
- [ ] 3.3 Определить pydantic-модели параметров/результата поиска в `models.py` (`QueryParam`, `LimitParam`, `SearchSymbolsResult` и элемент результата) согласно `specs/bybit-symbol-search/spec.md`
- [ ] 3.4 Реализовать `tools/search.py`: `search_symbols(client, query, limit)` — фильтрация по подстроке в `symbol`/`base_coin`/`quote_coin`, только `status == "Trading"`, `count`/`truncated`; проверить тестами сценарии из спеки (поиск по монете, по полному тикеру, пустой запрос, усечение по `limit`, исключение неторгуемых и деривативных пар)

## 4. Текущая цена

- [ ] 4.1 Определить модели результата `get_current_price` в `models.py` согласно `specs/bybit-current-price/spec.md`
- [ ] 4.2 Реализовать `tools/price.py`: `get_current_price(client, symbol)` — резолвинг через `resolver`, запрос `tickers?category=spot&symbol=...`, нормализация полей (`price`, `price_unit=quote_coin`, `change_pct_24h` округлён до двух знаков, `as_of` из конверта `time` в UTC ISO 8601), верхний регистр `symbol` на входе и выходе
- [ ] 4.3 Написать тесты на записанных фикстурах: обычная пара, тикер в нижнем регистре, несуществующий тикер (ошибка с упоминанием символа), пара не в статусе `Trading` (ошибка со статусом); проверить: `pytest tests/test_price.py` зелёный

## 5. История цен

- [ ] 5.1 Определить enum интервалов и маппинг на коды Bybit (`{"15m": "15", "1h": "60", "4h": "240", "1d": "D", "1w": "W", "1M": "M"}`) и модели `get_price_history` в `models.py` согласно `specs/bybit-price-history/spec.md`
- [ ] 5.2 Реализовать в `tools/history.py` оценку ожидаемого числа свечей по периоду и интервалу до похода в сеть и отказ (`TooManyCandles`) при превышении 5000 без обращения к Bybit
- [ ] 5.3 Реализовать пагинацию `get_kline` (запросы по `end`, сдвигаемому на минимальный полученный `startTime - 1`, до достижения `date_from` или пустого ответа), сборку полного набора свечей, сортировку по возрастанию `begin` и подсчёт `summary` по полному набору
- [ ] 5.4 Реализовать усечение результата до 300 последних свечей в `candles` с `candles_truncated`/`candles_returned`, сохраняя `summary` по полному набору
- [ ] 5.5 Написать тесты на записанных фикстурах (многостраничный ответ, включая случай, что требует более одного вызова `kline`): дневные свечи, длинный период с усечением, чрезмерно большой период (ошибка без сетевого вызова), несуществующий тикер, единицы цены для пары с нестандартной котируемой монетой (например `ETHBTC`); проверить: `pytest tests/test_history.py` зелёный

## 6. Аналитика

- [ ] 6.1 Скопировать `analytics/series.py` из `mcp-moex` без изменений (математика по OHLC не зависит от класса актива)
- [ ] 6.2 Перенести `analytics/stats.py` с правкой `ANNUALIZATION_FACTORS` на `{"1d": 365, "1w": 52, "1M": 12}`
- [ ] 6.3 Перенести `analytics/core.py` и `analytics/text.py` с правками: замена заметок (`DIVIDENDS_NOTE`/`BOND_NOTE`/`BENCHMARK_NOTE`/`CURRENCY_NOTE`) на формулировки для крипты из `design.md`, удаление ветки логики для облигаций, замена часового пояса MSK на UTC
- [ ] 6.4 Реализовать `analytics/build.py` и `tools/analytics.py`: валидацию входной истории (усечение, неподдерживаемый интервал, несогласованность `summary`/свечей, немонотонные/повторяющиеся `begin`, неположительные цены) и проверку совпадения `price_unit` для `compare_with_benchmark`/`compare_securities`, согласно `specs/bybit-price-analytics/spec.md`
- [ ] 6.5 Определить модели `compute_price_metrics`/`compare_with_benchmark`/`compare_securities` (параметры и результаты) в `models.py`
- [ ] 6.6 Написать тесты аналитики на синтетических историях (без сети): согласованный расчёт `change_pct`/волатильности/просадки/корреляции/беты, все сценарии отклонения из спеки, предупреждение о резком скачке цены (1.8x), разные котируемые монеты при сравнении; проверить: `pytest tests/test_analytics_*.py` зелёный

## 7. Сервер и точка входа

- [ ] 7.1 Реализовать `server.py`: `create_server()`, регистрация всех шести инструментов через `@server.tool(...)` с `readOnlyHint = true`, единые описания (порядок использования: `search_symbols` → `get_current_price`/`get_price_history` → инструменты анализа), общий `_guard`, транслирующий `BybitError` в `ToolError`
- [ ] 7.2 Реализовать CLI (`argparse`): `--transport {stdio,streamable-http}` (по умолчанию `stdio`), `--port` (по умолчанию 8000, только `127.0.0.1`), настройку логирования в stderr
- [ ] 7.3 Написать `tests/test_server.py`: `list_tools` возвращает ровно шесть инструментов с `readOnlyHint = true`, вызов инструмента с некорректными аргументами возвращает `isError = true` без трассировки; проверить: `pytest tests/test_server.py` зелёный

## 8. Проверка на реальном Bybit и документация

- [ ] 8.1 Написать `scripts/smoke_client.py` (по образцу `mcp-moex`): запускает сервер, вызывает все шесть инструментов на реальном Bybit по паре `BTCUSDT` и завершается кодом 0 при успехе
- [ ] 8.2 Прогнать `uv run python scripts/smoke_client.py` против реального Bybit и убедиться в успешном завершении
- [ ] 8.3 Написать `README.md` (по структуре `mcp-moex`): таблица инструментов, единицы цен, формат ошибок, запуск (`stdio`/`streamable-http`), пример подключения клиента, ограничения (только spot, без деривативов и приватных эндпоинтов)
- [ ] 8.4 Прогнать полный набор тестов (`uv run pytest`) и убедиться, что тесты не используют сеть и все проходят
