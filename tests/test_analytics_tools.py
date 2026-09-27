from datetime import date

import pytest

from mcp_bybit.errors import (
    HistoryInconsistent,
    HistoryTruncated,
    IntervalMismatch,
    IntervalNotSupported,
    NoHistoryData,
    QuoteCoinMismatch,
    TooFewCommonCandles,
)
from mcp_bybit.tools.analytics import compare_securities, compare_with_benchmark, compute_price_metrics

from .analytics_helpers import make_history

TODAY = date(2024, 2, 1)


async def test_compute_price_metrics_change_pct_matches_summary():
    history = make_history(closes=[100.0, 110.0, 121.0])
    result = await compute_price_metrics(history, TODAY)

    assert result.change_pct == history.summary.change_pct
    assert result.candles_used == 3
    assert result.max_drawdown.peak is None  # монотонный рост: просадки не было


async def test_compute_price_metrics_volatility_is_none_for_short_series():
    history = make_history(closes=[100.0, 110.0])
    result = await compute_price_metrics(history, TODAY)

    assert result.volatility_annualized_pct is None
    assert result.annualization_factor == 365


async def test_compute_price_metrics_drawdown_detected():
    history = make_history(closes=[100.0, 120.0, 90.0, 95.0, 121.0])
    result = await compute_price_metrics(history, TODAY)

    assert result.max_drawdown.depth_pct < 0
    assert result.max_drawdown.recovered_at is not None


async def test_split_like_jump_produces_warning_note():
    history = make_history(closes=[100.0, 100.0, 250.0, 251.0])
    result = await compute_price_metrics(history, TODAY)

    assert any("скачок ликвидности" in note for note in result.notes)


async def test_truncated_history_is_rejected():
    history = make_history(closes=[100.0, 110.0], truncated=True)
    with pytest.raises(HistoryTruncated):
        await compute_price_metrics(history, TODAY)


@pytest.mark.parametrize("interval", ["15m", "1h", "4h"])
async def test_intraday_interval_is_rejected(interval):
    history = make_history(closes=[100.0, 110.0], interval=interval, begins=[date(2024, 1, 5), date(2024, 1, 5)])
    with pytest.raises(IntervalNotSupported):
        await compute_price_metrics(history, TODAY)


async def test_no_candles_is_rejected():
    history = make_history(closes=[100.0]).model_copy(update={"candles": [], "summary": None})
    with pytest.raises(NoHistoryData):
        await compute_price_metrics(history, TODAY)


async def test_inconsistent_summary_is_rejected():
    history = make_history(closes=[100.0, 110.0])
    broken = history.model_copy(update={"summary": history.summary.model_copy(update={"end_price": 999.0})})
    with pytest.raises(HistoryInconsistent):
        await compute_price_metrics(broken, TODAY)


async def test_compare_with_benchmark_correlation_and_beta():
    history = make_history(symbol="ETHUSDT", closes=[100.0, 110.0, 121.0, 133.1])
    benchmark = make_history(symbol="BTCUSDT", closes=[200.0, 210.0, 220.0, 231.0])

    result = await compare_with_benchmark(history, benchmark, TODAY)

    assert result.symbol == "ETHUSDT"
    assert result.benchmark_symbol == "BTCUSDT"
    assert result.correlation is not None
    assert result.beta is not None


async def test_compare_securities_correlation():
    a = make_history(symbol="ETHUSDT", closes=[100.0, 105.0, 98.0, 110.0])
    b = make_history(symbol="SOLUSDT", closes=[50.0, 52.0, 49.0, 55.0])

    result = await compare_securities(a, b, TODAY)

    assert result.a_symbol == "ETHUSDT"
    assert result.b_symbol == "SOLUSDT"
    assert result.correlation is not None


async def test_interval_mismatch_between_histories_is_rejected():
    a = make_history(symbol="ETHUSDT", closes=[100.0, 110.0], interval="1d")
    b = make_history(symbol="SOLUSDT", closes=[50.0, 55.0], interval="1w")

    with pytest.raises(IntervalMismatch):
        await compare_securities(a, b, TODAY)


async def test_quote_coin_mismatch_is_rejected():
    a = make_history(symbol="ETHUSDT", closes=[100.0, 110.0], price_unit="USDT")
    b = make_history(symbol="ETHBTC", closes=[0.05, 0.052], price_unit="BTC")

    with pytest.raises(QuoteCoinMismatch, match="USDT.*BTC|BTC.*USDT"):
        await compare_securities(a, b, TODAY)


async def test_too_few_common_candles_is_rejected():
    a = make_history(symbol="ETHUSDT", closes=[100.0, 110.0], begins=[date(2024, 1, 1), date(2024, 1, 2)])
    b = make_history(symbol="SOLUSDT", closes=[50.0, 55.0], begins=[date(2024, 2, 1), date(2024, 2, 2)])

    with pytest.raises(TooFewCommonCandles):
        await compare_securities(a, b, TODAY)
