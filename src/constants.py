EMA_PERIOD: int = 200
RSI_PERIOD: int = 14
RSI_OVERBOUGHT: float = 70.0
RSI_OVERSOLD: float = 30.0
ATR_PERIOD: int = 14
ATR_AVG_WINDOW: int = 100
MAX_STOP_DISTANCE_PCT: float = 1.0
STOP_LOOKBACK: int = 20

H4_PERIOD: str = "4hour"
M15_PERIOD: str = "15min"
H4_SIZE: int = EMA_PERIOD + 10
M15_SIZE: int = max(ATR_PERIOD + ATR_AVG_WINDOW, RSI_PERIOD + 2) + 10

HTX_HOST: str = "api.hbdm.com"
HTX_BASE_API_URL: str = f"https://{HTX_HOST}"

HTX_GET_KLINES_API_PATH: str = "/linear-swap-ex/market/history/kline"
HTX_ORDER_API_PATH: str = "/linear-swap-api/v1/swap_cross_order"
HTX_ACCOUNT_INFO_API_PATH: str = "/linear-swap-api/v3/unified_account_info"

HTX_GET_KLINES_API_URL: str = HTX_BASE_API_URL + HTX_GET_KLINES_API_PATH
HTX_ORDER_API_URL: str = HTX_BASE_API_URL + HTX_ORDER_API_PATH
HTX_ACCOUNT_INFO_API_URL: str = HTX_BASE_API_URL + HTX_ACCOUNT_INFO_API_PATH

HTX_TIMEOUT: float = 10.0

TAKE_PROFIT: float = 0.03
STOP_LOSS: float = 0.01
AMOUNT_OF_VOLUME_FROM_DEPOSIT: float = 0.05
DEFAULT_LEVERAGE: int = 2
