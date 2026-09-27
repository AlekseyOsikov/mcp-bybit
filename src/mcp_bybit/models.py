"""Pydantic-модели входов и выходов инструментов.

Описания полей (`description`) попадают в JSON-схемы, которые видит агент, поэтому написаны для LLM.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

Interval = Literal["15m", "1h", "4h", "1d", "1w", "1M"]

# --- Входные параметры инструментов -------------------------------------------------------------

QueryParam = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=40),
    Field(
        description=(
            "Что искать: код монеты (например, «ETH», «BTC»), часть тикера или тикер целиком "
            "(например, «BTCUSDT»); регистр не важен."
        )
    ),
]

LimitParam = Annotated[
    int,
    Field(ge=1, le=20, description="Максимум результатов, от 1 до 20."),
]

SymbolParam = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=40, pattern=r"^[A-Za-z0-9]+$"),
    Field(
        description=(
            "Тикер спотовой пары на Bybit, например BTCUSDT, ETHUSDT, ETHBTC (регистр не важен). "
            "Если известна только монета, а не точный тикер, сначала найдите его через search_symbols."
        )
    ),
]

DateFromParam = Annotated[
    str,
    StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$"),
    Field(description="Начало периода, дата в формате YYYY-MM-DD (включительно), UTC.", examples=["2026-01-01"]),
]

DateTillParam = Annotated[
    str | None,
    Field(
        description=(
            "Конец периода, дата в формате YYYY-MM-DD (включительно), UTC. "
            "Если не указан, берётся сегодняшняя дата UTC."
        ),
        examples=["2026-09-10"],
    ),
]

IntervalParam = Annotated[
    Interval,
    Field(
        description=(
            "Размер свечи: 15m, 1h, 4h, 1d (день), 1w (неделя), 1M (месяц). "
            "Инструменты анализа (compute_price_metrics, compare_with_benchmark, compare_securities) "
            "поддерживают только 1d, 1w и 1M."
        )
    ),
]

# --- Результат search_symbols ---------------------------------------------------------------------


class SymbolHit(BaseModel):
    symbol: str = Field(description="Тикер для остальных инструментов (get_current_price, get_price_history).")
    base_coin: str = Field(description="Базовая монета пары.")
    quote_coin: str = Field(description="Котируемая монета пары (единица цены).")
    status: str = Field(description="Статус пары на Bybit; поиск возвращает только пары со статусом Trading.")


class SearchSymbolsResult(BaseModel):
    query: str = Field(description="Запрос после обрезки пробелов.")
    results: list[SymbolHit] = Field(description="Найденные пары; точное совпадение тикера идёт первым.")
    count: int = Field(description="Число элементов в results.")
    truncated: bool = Field(description="true, если найдено больше, чем limit: уточните запрос.")


# --- Результат get_current_price ------------------------------------------------------------------


class PriceResult(BaseModel):
    symbol: str = Field(description="Тикер в каноническом верхнем регистре.")
    base_coin: str = Field(description="Базовая монета пары.")
    quote_coin: str = Field(description="Котируемая монета пары.")
    price: float = Field(description="Цена последней сделки, в единицах price_unit.")
    price_unit: str = Field(description="Единица price: котируемая монета пары (равна quote_coin).")
    bid_price: float = Field(description="Лучшая цена покупки (лучший bid).")
    ask_price: float = Field(description="Лучшая цена продажи (лучший ask).")
    change_pct_24h: float = Field(description="Изменение цены за последние 24 часа в %, округлено до двух знаков.")
    high_24h: float = Field(description="Максимальная цена за последние 24 часа.")
    low_24h: float = Field(description="Минимальная цена за последние 24 часа.")
    volume_24h: float = Field(description="Объём торгов за 24 часа, в базовой монете.")
    turnover_24h: float = Field(description="Оборот торгов за 24 часа, в котируемой монете.")
    as_of: str = Field(
        description="Время формирования ответа биржей, ISO 8601, UTC. Это время ответа, а не отдельная метка последней сделки."
    )
    trading_status: str = Field(description="Статус пары на Bybit (например, Trading).")


# --- Результат get_price_history -------------------------------------------------------------------


class Candle(BaseModel):
    begin: str = Field(description="Начало свечи, ISO 8601, UTC.")
    open: float
    high: float
    low: float
    close: float
    volume: float = Field(description="Объём торгов свечи, в базовой монете.")
    turnover: float = Field(description="Оборот свечи, в котируемой монете.")


class HistorySummary(BaseModel):
    candles_count: int = Field(description="Число свечей за весь период (не только возвращённых).")
    start_price: float = Field(description="Цена открытия первой свечи периода.")
    end_price: float = Field(description="Цена закрытия последней свечи периода.")
    min_price: float = Field(description="Наименьшая цена (low) за период.")
    max_price: float = Field(description="Наибольшая цена (high) за период.")
    change_abs: float = Field(description="end_price - start_price.")
    change_pct: float = Field(description="Изменение за период в %: (end_price - start_price) / start_price * 100.")
    first_candle: str = Field(description="Начало первой свечи периода, ISO 8601, UTC.")
    last_candle: str = Field(description="Начало последней свечи периода, ISO 8601, UTC.")


class HistoryResult(BaseModel):
    symbol: str = Field(description="Тикер в каноническом верхнем регистре.")
    base_coin: str = Field(description="Базовая монета пары.")
    quote_coin: str = Field(description="Котируемая монета пары.")
    price_unit: str = Field(description="Единица цен свечей: котируемая монета пары (равна quote_coin).")
    interval: Interval = Field(description="Размер свечи.")
    date_from: str = Field(description="Начало периода, YYYY-MM-DD, UTC.")
    date_till: str = Field(description="Конец периода, YYYY-MM-DD, UTC.")
    summary: HistorySummary | None = Field(
        description="Сводка по всем свечам периода; null, если за период нет данных."
    )
    candles: list[Candle] = Field(description="Свечи по возрастанию времени (не более 300 последних).")
    candles_returned: int = Field(description="Сколько свечей возвращено в candles.")
    candles_truncated: bool = Field(description="true: свечей больше, чем возвращено; сводка учитывает все.")
    message: str | None = Field(default=None, description="Пояснение, например, что за период нет торгов.")


# --- Анализ истории (bybit-price-analytics) ---------------------------------------------------------
# Входом служит результат get_price_history целиком, без преобразований.

_HISTORY_HINT = (
    "результат get_price_history целиком, без изменений (свечи и summary из одного вызова, не усечённые, "
    "interval 1d, 1w или 1M). Тикер сначала найдите через search_symbols."
)

HistoryParam = Annotated[HistoryResult, Field(description=f"История пары: {_HISTORY_HINT}")]

BenchmarkHistoryParam = Annotated[
    HistoryResult,
    Field(
        description=(
            f"История эталонной пары (например, BTCUSDT — обычный рыночный эталон для крипты): {_HISTORY_HINT} "
            "Получите её с тем же interval, что и history, и с той же котируемой монетой (quote_coin)."
        )
    ),
]

HistoryAParam = Annotated[HistoryResult, Field(description=f"История пары A: {_HISTORY_HINT}")]

HistoryBParam = Annotated[
    HistoryResult,
    Field(
        description=(
            f"История пары B: {_HISTORY_HINT} "
            "Получите её с тем же interval и с той же котируемой монетой (quote_coin), что и history_a."
        )
    ),
]


class Drawdown(BaseModel):
    depth_pct: float = Field(
        description="Глубина просадки по ценам закрытия в %, не больше нуля (например, -25.0); 0, если просадки не было."
    )
    peak: str | None = Field(description="Начало свечи, на закрытии которой был пик перед просадкой; null без просадки.")
    trough: str | None = Field(description="Начало свечи, на закрытии которой было дно; null без просадки.")
    recovered_at: str | None = Field(
        description="Начало первой свечи, закрытие которой вернулось к пику; null, если цена не восстановилась или просадки не было."
    )


class PeriodChange(BaseModel):
    begin: str = Field(description="Начало свечи, ISO 8601, UTC.")
    change_pct: float = Field(
        description="Изменение цены за свечу в %: первая свеча от open, остальные от close предыдущей."
    )
    partial: bool = Field(description="true: период свечи ещё не завершён (например, текущий месяц).")


class BenchmarkPeriod(BaseModel):
    begin: str = Field(description="Начало общей свечи, ISO 8601, UTC.")
    change_pct: float = Field(description="Изменение цены пары за период в %.")
    benchmark_change_pct: float = Field(description="Изменение эталонной пары за период в %.")
    difference_pp: float = Field(description="change_pct - benchmark_change_pct, в процентных пунктах.")
    partial: bool = Field(description="true: период свечи ещё не завершён.")


class PairPeriod(BaseModel):
    begin: str = Field(description="Начало общей свечи, ISO 8601, UTC.")
    a_change_pct: float = Field(description="Изменение цены пары A за период в %.")
    b_change_pct: float = Field(description="Изменение цены пары B за период в %.")
    difference_pp: float = Field(description="a_change_pct - b_change_pct, в процентных пунктах.")
    partial: bool = Field(description="true: период свечи ещё не завершён.")


_NOTES = (
    "Предупреждения на русском (комиссии и доходность держателя не учтены, незавершённая свеча, возможный "
    "скачок ликвидности, малая выборка, суженное окно). Передайте их пользователю вместе с числами."
)
_TEXT = "Готовый русский текст итога с числами, замечаниями и оговорками: отправляйте пользователю как есть."


class MetricsResult(BaseModel):
    symbol: str = Field(description="Тикер в каноническом верхнем регистре.")
    price_unit: str = Field(description="Единица цены: котируемая монета пары.")
    interval: Interval = Field(description="Размер свечи.")
    first_candle: str = Field(description="Начало первой свечи периода расчёта, ISO 8601, UTC.")
    last_candle: str = Field(description="Начало последней свечи периода расчёта, ISO 8601, UTC.")
    candles_used: int = Field(description="Число свечей в расчёте.")
    change_pct: float = Field(description="Изменение цены за период в %; совпадает со summary.change_pct истории.")
    volatility_annualized_pct: float | None = Field(
        description=(
            "Годовая волатильность в %: стандартное отклонение изменений между соседними закрытиями, "
            "приведённое к году; null, если свечей меньше трёх."
        )
    )
    annualization_factor: int = Field(
        description="Число периодов в году, использованное для приведения (1d 365, 1w 52, 1M 12)."
    )
    max_drawdown: Drawdown = Field(description="Максимальная просадка по ценам закрытия.")
    current_drawdown_pct: float = Field(
        description="Текущая просадка в %, не больше нуля: от максимального закрытия периода до последнего закрытия."
    )
    periods: list[PeriodChange] = Field(description="Изменение цены по каждой свече по возрастанию времени.")
    notes: list[str] = Field(description=_NOTES)
    text: str = Field(description=_TEXT)


class BenchmarkComparison(BaseModel):
    symbol: str = Field(description="Тикер сравниваемой пары.")
    price_unit: str = Field(description="Единица цены пары.")
    benchmark_symbol: str = Field(description="Тикер эталонной пары.")
    interval: Interval = Field(description="Размер свечи обеих историй.")
    first_candle: str = Field(description="Начало первой общей свечи, ISO 8601, UTC.")
    last_candle: str = Field(description="Начало последней общей свечи, ISO 8601, UTC.")
    candles_common: int = Field(description="Число общих свечей, по которым идёт расчёт.")
    change_pct: float = Field(description="Изменение цены пары за общее окно в %.")
    benchmark_change_pct: float = Field(description="Изменение эталонной пары за общее окно в %.")
    difference_pp: float = Field(
        description="change_pct - benchmark_change_pct в процентных пунктах; больше нуля: пара опередила эталон."
    )
    beta: float | None = Field(
        description=(
            "Бета: ковариация изменений пары и эталона между соседними закрытиями, делённая на дисперсию эталона; "
            "null, если изменений меньше трёх или разброс нулевой."
        )
    )
    correlation: float | None = Field(
        description="Корреляция изменений между соседними закрытиями, от -1 до 1; null при тех же условиях, что и beta."
    )
    max_drawdown: Drawdown = Field(description="Максимальная просадка пары в общем окне.")
    benchmark_max_drawdown: Drawdown = Field(description="Максимальная просадка эталона в общем окне.")
    periods: list[BenchmarkPeriod] = Field(description="Изменения пары и эталона по каждой общей свече.")
    notes: list[str] = Field(description=_NOTES)
    text: str = Field(description=_TEXT)


class PairComparison(BaseModel):
    a_symbol: str = Field(description="Тикер пары A (history_a).")
    a_price_unit: str = Field(description="Единица цены пары A.")
    b_symbol: str = Field(description="Тикер пары B (history_b).")
    b_price_unit: str = Field(description="Единица цены пары B.")
    interval: Interval = Field(description="Размер свечи обеих историй.")
    first_candle: str = Field(description="Начало первой общей свечи, ISO 8601, UTC.")
    last_candle: str = Field(description="Начало последней общей свечи, ISO 8601, UTC.")
    candles_common: int = Field(description="Число общих свечей, по которым идёт расчёт.")
    a_change_pct: float = Field(description="Изменение цены пары A за общее окно в %.")
    b_change_pct: float = Field(description="Изменение цены пары B за общее окно в %.")
    difference_pp: float = Field(
        description="a_change_pct - b_change_pct в процентных пунктах; больше нуля: A опередила B."
    )
    correlation: float | None = Field(
        description="Корреляция изменений между соседними закрытиями, от -1 до 1; null, если изменений меньше трёх или разброс нулевой."
    )
    a_max_drawdown: Drawdown = Field(description="Максимальная просадка A в общем окне.")
    b_max_drawdown: Drawdown = Field(description="Максимальная просадка B в общем окне.")
    periods: list[PairPeriod] = Field(description="Изменения A и B по каждой общей свече.")
    notes: list[str] = Field(description=_NOTES)
    text: str = Field(description=_TEXT)
