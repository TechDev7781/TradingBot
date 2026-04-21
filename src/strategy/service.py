import logging
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange

from src.constants import (
    ATR_AVG_WINDOW,
    ATR_PERIOD,
    EMA_PERIOD,
    H4_PERIOD,
    H4_SIZE,
    M15_PERIOD,
    M15_SIZE,
    MAX_STOP_DISTANCE_PCT,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    RSI_PERIOD,
    STOP_LOOKBACK,
)
from src.htx.service import HtxService
from src.schemas import (
    BEARISH_PATTERNS,
    BULLISH_PATTERNS,
    FilterResultSchema,
    KlineSchema,
    NotificationSchema,
    SideEnum,
    StrategyDecisionSchema,
)
from src.telegram.service import TelegramService

logger = logging.getLogger(__name__)


class StrategyService:
    @classmethod
    def _to_frame(cls, klines: Sequence[KlineSchema]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "open": [k.open for k in klines],
                "high": [k.high for k in klines],
                "low": [k.low for k in klines],
                "close": [k.close for k in klines],
            }
        )

    @classmethod
    def _ema(cls, closes: Sequence[float], period: int) -> float:
        series = pd.Series(closes, dtype="float64")
        value = (
            EMAIndicator(close=series, window=period, fillna=False)
            .ema_indicator()
            .iloc[-1]
        )
        if pd.isna(value):
            raise ValueError(f"Недостаточно данных для EMA({period}): {len(closes)}")
        return float(value)

    @classmethod
    def _rsi(cls, closes: Sequence[float], period: int) -> float:
        series = pd.Series(closes, dtype="float64")
        value = RSIIndicator(close=series, window=period, fillna=False).rsi().iloc[-1]
        if pd.isna(value):
            raise ValueError(f"Недостаточно данных для RSI({period}): {len(closes)}")
        return float(value)

    @classmethod
    def _atr_series(cls, klines: Sequence[KlineSchema], period: int) -> list[float]:
        df = cls._to_frame(klines)
        series = AverageTrueRange(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            window=period,
            fillna=False,
        ).average_true_range()
        values = series.dropna().tolist()
        if not values:
            raise ValueError(f"Недостаточно данных для ATR({period}): {len(klines)}")
        return [float(v) for v in values]

    @classmethod
    def _check_pattern(cls, notification: NotificationSchema) -> FilterResultSchema:
        if notification.side == SideEnum.LONG:
            ok = notification.pattern in BULLISH_PATTERNS
            expected = "bullish"
        else:
            ok = notification.pattern in BEARISH_PATTERNS
            expected = "bearish"
        return FilterResultSchema(
            name="pattern",
            passed=ok,
            details=(
                f"side={notification.side.value} pattern={notification.pattern.value} "
                f"expected_group={expected}"
            ),
        )

    @classmethod
    def _check_global_trend(
        cls, side: SideEnum, h4_closes: Sequence[float], price: float
    ) -> FilterResultSchema:
        ema200 = cls._ema(h4_closes, EMA_PERIOD)
        if side == SideEnum.LONG:
            passed = price > ema200
            rule = "price>ema200"
        else:
            passed = price < ema200
            rule = "price<ema200"
        return FilterResultSchema(
            name="H4_trend",
            passed=passed,
            details=f"rule={rule} price={price:.6f} ema200={ema200:.6f}",
        )

    @classmethod
    def _check_rsi(
        cls, side: SideEnum, m15_closes: Sequence[float]
    ) -> FilterResultSchema:
        value = cls._rsi(m15_closes, RSI_PERIOD)
        if side == SideEnum.LONG:
            passed = value < RSI_OVERBOUGHT
            rule = f"RSI<{RSI_OVERBOUGHT}"
        else:
            passed = value > RSI_OVERSOLD
            rule = f"RSI>{RSI_OVERSOLD}"
        return FilterResultSchema(
            name="RSI",
            passed=passed,
            details=f"rule={rule} value={value:.2f}",
        )

    @classmethod
    def _check_atr(cls, m15_klines: Sequence[KlineSchema]) -> FilterResultSchema:
        series = cls._atr_series(m15_klines, ATR_PERIOD)
        if len(series) < ATR_AVG_WINDOW:
            return FilterResultSchema(
                name="ATR",
                passed=False,
                details=(
                    f"series_len={len(series)} < required={ATR_AVG_WINDOW} "
                    f"(нужно больше M15-свечей)"
                ),
            )
        current = series[-1]
        avg = sum(series[-ATR_AVG_WINDOW:]) / ATR_AVG_WINDOW
        return FilterResultSchema(
            name="ATR",
            passed=current > avg,
            details=f"rule=ATR>avg{ATR_AVG_WINDOW} current={current:.6f} avg={avg:.6f}",
        )

    @classmethod
    def _check_stop_distance(
        cls, side: SideEnum, price: float, m15_klines: Sequence[KlineSchema]
    ) -> FilterResultSchema:
        recent = m15_klines[-STOP_LOOKBACK:]
        if side == SideEnum.LONG:
            reference = min(k.low for k in recent)
            distance_pct = (price - reference) / price * 100
            rule = f"0<distance<={MAX_STOP_DISTANCE_PCT}% (low за {STOP_LOOKBACK} M15)"
        else:
            reference = max(k.high for k in recent)
            distance_pct = (reference - price) / price * 100
            rule = f"0<distance<={MAX_STOP_DISTANCE_PCT}% (high за {STOP_LOOKBACK} M15)"
        passed = 0 < distance_pct <= MAX_STOP_DISTANCE_PCT
        return FilterResultSchema(
            name="stop_distance",
            passed=passed,
            details=(
                f"rule={rule} price={price:.6f} reference={reference:.6f} "
                f"distance={distance_pct:.3f}%"
            ),
        )

    @classmethod
    def _check_indicators(
        cls,
        notification: NotificationSchema,
        h4_klines: Sequence[KlineSchema],
        m15_klines: Sequence[KlineSchema],
    ) -> StrategyDecisionSchema:
        price = notification.close
        side = notification.side
        h4_closes = [k.close for k in h4_klines]
        m15_closes = [k.close for k in m15_klines]

        logger.info(
            "старт оценки ticker=%s side=%s pattern=%s price=%.6f "
            "(H4 свечей=%d, M15 свечей=%d)",
            notification.ticker,
            side.value,
            notification.pattern.value,
            price,
            len(h4_klines),
            len(m15_klines),
        )

        checks: list[FilterResultSchema] = [
            cls._check_pattern(notification),
            cls._check_global_trend(side, h4_closes, price),
            cls._check_rsi(side, m15_closes),
            cls._check_atr(m15_klines),
            cls._check_stop_distance(side, price, m15_klines),
        ]

        for c in checks:
            status = "PASS" if c.passed else "FAIL"
            logger.info("  [%s] %s — %s", status, c.name, c.details)

        decision = StrategyDecisionSchema(
            should_enter=all(c.passed for c in checks),
            side=side,
            checks=checks,
        )

        if decision.should_enter:
            logger.info(
                "✅ ВХОД РАЗРЕШЁН side=%s ticker=%s price=%.6f",
                side.value,
                notification.ticker,
                price,
            )
        else:
            failed_names = ", ".join(c.name for c in decision.failed)
            logger.warning(
                "ВХОД ОТКЛОНЁН ticker=%s side=%s. Провалены фильтры: [%s]",
                notification.ticker,
                side.value,
                failed_names,
            )
            for c in decision.failed:
                logger.warning("    ↳ причина %s: %s", c.name, c.details)

        return decision

    @classmethod
    async def check(cls, schema: NotificationSchema) -> None:
        logger.info("Получен webhook от TradingView: %s", schema.model_dump_json())

        await TelegramService.broadcast(
            "Получен webhook от TradingView:\n"
            f"Тикер: {schema.ticker.value}\n"
            f"Сторона: {schema.side.value}\n"
            f"Паттерн: {schema.pattern.value}\n"
            f"Цена: {schema.close:.6f}\n"
        )

        time = datetime.now(timezone(timedelta(hours=3)))
        if time.hour < 9 and time.hour > 1:
            await TelegramService.broadcast(
                "Сделка не размещена из за нерабочего времени\n"
                f"Тикер: {schema.ticker.value}\n"
                f"Сторона: {schema.side.value}\n"
                f"Паттерн: {schema.pattern.value}\n"
                f"Цена: {schema.close:.6f}\n\n"
            )
            return

        try:
            h4_klines = await HtxService.get_klines(schema.ticker, H4_PERIOD, H4_SIZE)
            m15_klines = await HtxService.get_klines(
                schema.ticker, M15_PERIOD, M15_SIZE
            )

            decision = cls._check_indicators(
                schema, h4_klines=h4_klines, m15_klines=m15_klines
            )

            if not decision.should_enter:
                failed_lines = "\n".join(
                    f"- {c.name}: {c.details}" for c in decision.failed
                )
                await TelegramService.broadcast(
                    "Сделка не размещена\n"
                    f"Тикер: {schema.ticker.value}\n"
                    f"Сторона: {schema.side.value}\n"
                    f"Паттерн: {schema.pattern.value}\n"
                    f"Цена: {schema.close:.6f}\n\n"
                    f"Провалены фильтры:\n{failed_lines}"
                )
                return

            action = "buy" if decision.side == SideEnum.LONG else "sell"
            await HtxService.place_order(
                action=action,
                symbol=schema.ticker,
                price=schema.close,
            )

            await TelegramService.broadcast(
                "Сделка размещена\n"
                f"Тикер: {schema.ticker.value}\n"
                f"Сторона: {schema.side.value}\n"
                f"Паттерн: {schema.pattern.value}\n"
                f"Цена: {schema.close:.6f}\n"
            )
        except Exception as e:
            logger.exception("Ошибка при обработке webhook: %s", e)
            await TelegramService.broadcast(f"Ошибка при обработке webhook: {e}")
