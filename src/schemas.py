from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SideEnum(Enum):
    LONG = "long"
    SHORT = "short"


class PatternEnum(Enum):
    BULLISH_FLAG = "bullish_flag"
    BULLISH_PENNANT = "bullish_pennant"
    FALLING_WEDGE = "falling_wedge"

    BEARISH_FLAG = "bearish_flag"
    BEARISH_PENNANT = "bearish_pennant"
    RISING_WEDGE = "rising_wedge"

    TRIANGLE = "triangle"
    RECTANGLE = "rectangle"


class TickerEnum(Enum):
    BTCUSDT = "BTCUSDT"
    ETHUSDT = "ETHUSDT"
    SOLUSDT = "SOLUSDT"


ticker_to_htx_code = {
    TickerEnum.BTCUSDT: "BTC-USDT",
    TickerEnum.ETHUSDT: "ETH-USDT",
    TickerEnum.SOLUSDT: "SOL-USDT",
}

ticker_to_contract_size = {
    TickerEnum.BTCUSDT: 0.001,
    TickerEnum.ETHUSDT: 0.01,
    TickerEnum.SOLUSDT: 1.0,
}


class ExchangeEnum(Enum):
    HTX = "HTX"


BULLISH_PATTERNS: frozenset[PatternEnum] = frozenset(
    {
        PatternEnum.BULLISH_FLAG,
        PatternEnum.BULLISH_PENNANT,
        PatternEnum.FALLING_WEDGE,
        PatternEnum.TRIANGLE,
        PatternEnum.RECTANGLE,
    }
)
BEARISH_PATTERNS: frozenset[PatternEnum] = frozenset(
    {
        PatternEnum.BEARISH_FLAG,
        PatternEnum.BEARISH_PENNANT,
        PatternEnum.RISING_WEDGE,
        PatternEnum.TRIANGLE,
        PatternEnum.RECTANGLE,
    }
)


class NotificationSchema(BaseModel):
    ticker: TickerEnum
    exchange: ExchangeEnum
    side: SideEnum
    pattern: PatternEnum
    timeframe: str
    close: float = Field(gt=0)
    time: str
    volume: float


class KlineSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    timestamp: int | None = None


class FilterResultSchema(BaseModel):
    name: str
    passed: bool
    details: str


class StrategyDecisionSchema(BaseModel):
    should_enter: bool
    side: SideEnum
    checks: list[FilterResultSchema]

    @property
    def failed(self) -> list[FilterResultSchema]:
        return [c for c in self.checks if not c.passed]
