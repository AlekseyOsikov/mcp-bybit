"""Инструменты анализа истории: метрики одной пары и два вида сравнения. Без сети и без состояния."""

from datetime import date

from ..analytics import build
from ..analytics.series import validate_history
from ..models import BenchmarkComparison, HistoryResult, MetricsResult, PairComparison

_INPUT_RULES = """\
Параметры принимают результат get_price_history целиком, без изменений (свечи и summary из одного вызова): \
не пересчитывайте, не сокращайте и не правьте их. Историю пары сначала получите через get_price_history, \
а если известна только монета, тикер найдите через search_symbols. Для длинных периодов берите interval = \
"1w" или "1M": усечённая история (свечей больше 300) и внутридневные свечи (15m, 1h, 4h) не принимаются."""

_CAVEATS = """\
Считается изменение цены, а не доходность держателя: комиссии, вознаграждения и эйрдропы не учитываются \
(при подозрении на резкий скачок ликвидности или миграцию контракта в notes будет предупреждение). Все числа \
посчитаны сервером; в notes лежат предупреждения, в text готовый русский текст: передавайте их пользователю \
вместе с числами."""

METRICS_DESCRIPTION = f"""\
Метрики одной спотовой пары Bybit за период по её истории: изменение цены, годовая волатильность, \
максимальная и текущая просадка и изменение по каждой свече (по месяцам, неделям или дням).

{_INPUT_RULES}

Для сравнения пары с эталоном используйте compare_with_benchmark, для сравнения двух пар compare_securities.

{_CAVEATS}"""

BENCHMARK_DESCRIPTION = f"""\
Сравнение спотовой пары с эталонной по общим датам: изменение цены пары и эталона, разница в процентных \
пунктах (опережала ли пара эталон), бета, корреляция, максимальные просадки и таблица по периодам. Обычный \
рыночный эталон для крипты — BTCUSDT, но подойдёт любая пара с той же котируемой монетой.

В history передайте историю пары, в benchmark_history историю эталона: получите обе через get_price_history \
с одним и тем же interval и одним периодом и передайте без изменений. Котируемая монета (quote_coin) обеих \
историй должна совпадать — иначе цены напрямую не сравнимы.

{_INPUT_RULES}

{_CAVEATS}"""

SECURITIES_DESCRIPTION = f"""\
Сравнение двух спотовых пар между собой по общим датам: изменение цены каждой, разница A минус B в \
процентных пунктах, корреляция, максимальные просадки и таблица по периодам. Беты нет.

В history_a и history_b передайте истории двух пар: получите обе через get_price_history с одним и тем же \
interval и одним периодом и передайте без изменений. Котируемая монета (quote_coin) обеих историй должна \
совпадать — иначе цены напрямую не сравнимы.

{_INPUT_RULES}

{_CAVEATS}"""


async def compute_price_metrics(history: HistoryResult, today: date) -> MetricsResult:
    """Метрики одной пары; `today` (UTC) нужен для признака незавершённой свечи."""
    return build.metrics(validate_history(history, "history"), today)


async def compare_with_benchmark(
    history: HistoryResult, benchmark_history: HistoryResult, today: date
) -> BenchmarkComparison:
    """Пара против эталона по общим датам."""
    series = validate_history(history, "history")
    benchmark = validate_history(benchmark_history, "benchmark_history")
    return build.benchmark(series, benchmark, today)


async def compare_securities(history_a: HistoryResult, history_b: HistoryResult, today: date) -> PairComparison:
    """Две пары между собой по общим датам."""
    a = validate_history(history_a, "history_a")
    b = validate_history(history_b, "history_b")
    return build.pair(a, b, today)
