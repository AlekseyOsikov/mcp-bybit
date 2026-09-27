"""Доменные ошибки сервера: каждая несёт текст для LLM (что случилось и что делать)."""

ANALYSIS_INTERVALS = "1d, 1w, 1M"


class BybitError(Exception):
    """Базовая ошибка; `str(error)` можно показывать агенту как есть."""


class BybitUnavailable(BybitError):
    """Bybit не ответил или ответил ошибкой (таймаут, сеть, статус не 2xx, retCode != 0, неразборчивый ответ)."""

    def __init__(self, detail: str = "") -> None:
        message = "Bybit временно недоступен. Повторите запрос позже."
        if detail:
            message = f"{message} Подробности: {detail}"
        super().__init__(message)


class SymbolNotFound(BybitError):
    """Такого символа нет среди торгуемых спотовых пар Bybit."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        super().__init__(
            f"Спотовая пара «{symbol}» не найдена на Bybit. "
            "Найдите тикер через инструмент search_symbols (по коду монеты или части тикера) и повторите запрос."
        )


class UnsupportedCategory(BybitError):
    """Символ существует на Bybit, но только в категории деривативов (linear/inverse/option), а не в spot."""

    def __init__(self, symbol: str, category: str) -> None:
        self.symbol = symbol
        self.category = category
        super().__init__(
            f"«{symbol}» торгуется на Bybit только в категории «{category}» (деривативы), а не как спотовая пара. "
            "Этот сервер работает только со спотовым рынком (category = spot); деривативы не поддерживаются."
        )


class SymbolNotTrading(BybitError):
    """Пара найдена, но её статус отличен от Trading (приостановлена, делистнута, ещё не запущена)."""

    def __init__(self, symbol: str, status: str) -> None:
        self.symbol = symbol
        self.status = status
        super().__init__(
            f"Пара «{symbol}» найдена, но её статус «{status}», торги по ней сейчас недоступны. "
            "Проверьте тикер через инструмент search_symbols."
        )


class TooManyCandles(BybitError):
    """За запрошенный период слишком много свечей для обработки."""

    def __init__(self, interval: str, max_candles: int) -> None:
        self.interval = interval
        self.max_candles = max_candles
        finer = {"15m": "1h, 4h, 1d, 1w или 1M", "1h": "4h, 1d, 1w или 1M", "4h": "1d, 1w или 1M", "1d": "1w или 1M", "1w": "1M"}.get(
            interval
        )
        advice = f"Выберите более крупный interval ({finer}) или сократите период." if finer else "Сократите период."
        super().__init__(
            f"За запрошенный период больше {max_candles} свечей с интервалом «{interval}». {advice}"
        )


class InvalidArgument(BybitError):
    """Аргументы инструмента неверны по смыслу (например, начало периода позже конца)."""


# --- Анализ переданной истории (bybit-price-analytics) ------------------------------------------
# Каждая ошибка называет параметр, чья история отклонена: клиент должен знать, какую получить заново.


class HistoryTruncated(BybitError):
    """В истории свечей меньше, чем за период: сводка учитывает больше, чем видно в свечах."""

    def __init__(self, param: str) -> None:
        self.param = param
        super().__init__(
            f"Параметр {param}: история усечена (candles_truncated = true), считать по неполному ряду нельзя. "
            'Получите историю через get_price_history с более крупным interval (например, "1w" или "1M") '
            "или за более короткий период и повторите вызов."
        )


class IntervalNotSupported(BybitError):
    """Анализ не поддерживает интервал переданной истории (внутридневные свечи)."""

    def __init__(self, param: str, interval: str) -> None:
        self.param = param
        self.interval = interval
        super().__init__(
            f"Параметр {param}: интервал «{interval}» для анализа не поддерживается. "
            f"Поддерживаются: {ANALYSIS_INTERVALS}. Получите историю через get_price_history с interval = "
            '"1d" (короткие периоды), "1w" или "1M" и повторите вызов.'
        )


class NoHistoryData(BybitError):
    """В переданной истории нет свечей."""

    def __init__(self, param: str) -> None:
        self.param = param
        super().__init__(
            f"Параметр {param}: за период нет данных (свечей нет, summary = null). "
            "Возможно, торгов не было или пара ещё не торговалась. Получите историю через get_price_history "
            "за другой период и повторите вызов."
        )


class HistoryInconsistent(BybitError):
    """Свечи не согласованы со сводкой или сами по себе неверны: история изменена или повреждена."""

    def __init__(self, param: str, detail: str) -> None:
        self.param = param
        self.detail = detail
        super().__init__(
            f"Параметр {param}: история изменена или повреждена ({detail}). "
            "Получите историю заново через get_price_history и передайте результат без изменений."
        )


class IntervalMismatch(BybitError):
    """У двух сравниваемых историй разные интервалы свечей."""

    def __init__(self, param_a: str, interval_a: str, param_b: str, interval_b: str) -> None:
        super().__init__(
            f"Интервалы историй различаются: {param_a} = «{interval_a}», {param_b} = «{interval_b}». "
            "Получите обе истории через get_price_history с одним и тем же interval и повторите вызов."
        )


class QuoteCoinMismatch(BybitError):
    """У двух сравниваемых историй разная котируемая монета (price_unit): цены напрямую не сравнимы."""

    def __init__(self, param_a: str, unit_a: str, param_b: str, unit_b: str) -> None:
        super().__init__(
            f"У сравниваемых историй разная котируемая монета: {param_a} = «{unit_a}», {param_b} = «{unit_b}». "
            "Цены в разных монетах напрямую не сравнимы. Выберите пары с одинаковой котируемой монетой "
            "(например, обе к USDT) и повторите вызов."
        )


class TooFewCommonCandles(BybitError):
    """У двух историй меньше двух общих свечей."""

    def __init__(self, common: int) -> None:
        self.common = common
        super().__init__(
            f"Общий период двух историй слишком короткий: общих свечей {common}, нужно не меньше двух. "
            "Получите обе истории через get_price_history за более длинный период или с более мелким interval "
            "и повторите вызов."
        )
