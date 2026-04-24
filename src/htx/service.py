import base64
import hashlib
import hmac
import logging
import math
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import quote, urlencode

import httpx

from src.config import settings
from src.constants import (
    AMOUNT_OF_VOLUME_FROM_DEPOSIT,
    DEFAULT_LEVERAGE,
    HTX_ACCOUNT_INFO_API_PATH,
    HTX_ACCOUNT_INFO_API_URL,
    HTX_GET_KLINES_API_URL,
    HTX_HOST,
    HTX_ORDER_API_PATH,
    HTX_ORDER_API_URL,
    HTX_TIMEOUT,
    STOP_LOSS,
    TAKE_PROFIT,
)
from src.schemas import (
    KlineSchema,
    TickerEnum,
    ticker_to_contract_size,
    ticker_to_htx_code,
)

logger = logging.getLogger(__name__)


class HtxService:
    @classmethod
    async def _signed_post(
        cls,
        url: str,
        path: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        if not settings.htx_api_key or not settings.htx_api_secret:
            raise RuntimeError("HTX API ключи не заданы в .env")

        auth = {
            "AccessKeyId": settings.htx_api_key,
            "SignatureMethod": "HmacSHA256",
            "SignatureVersion": "2",
            "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        }
        auth["Signature"] = cls._sign("POST", path, auth, settings.htx_api_secret)

        signed_url = f"{url}?{urlencode(auth)}"

        async with httpx.AsyncClient(timeout=HTX_TIMEOUT, verify=False) as client:
            resp = await client.post(
                signed_url,
                json=body,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        is_ok = data.get("status") == "ok" or data.get("code") == 200
        if not is_ok:
            meta = {
                "status": data.get("status"),
                "code": data.get("code"),
                "err_code": data.get("err_code"),
                "err_msg": data.get("err_msg"),
                "message": data.get("message"),
                "ts": data.get("ts"),
            }
            raise RuntimeError(f"HTX ответ с ошибкой ({path}): {meta}")

        return data

    @staticmethod
    def _sign(
        method: str,
        path: str,
        params: dict[str, str],
        secret_key: str,
    ) -> str:
        encoded = "&".join(
            f"{k}={quote(str(params[k]), safe='')}" for k in sorted(params)
        )
        payload = f"{method.upper()}\n{HTX_HOST}\n{path}\n{encoded}"
        digest = hmac.new(
            secret_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(digest).decode()

    @classmethod
    def _calc_volume(
        cls, symbol: TickerEnum, price: float, balance: float, lever_rate: int
    ) -> int:
        contract_size = ticker_to_contract_size[symbol]
        margin_target_usdt = balance * AMOUNT_OF_VOLUME_FROM_DEPOSIT
        notional_target_usdt = margin_target_usdt * lever_rate
        contracts_float = notional_target_usdt / (price * contract_size)
        # On HTX volume is integer contracts; ceil avoids undersizing the position.
        volume = math.ceil(contracts_float)
        if volume < 1:
            raise RuntimeError(
                f"Депозит слишком мал для {AMOUNT_OF_VOLUME_FROM_DEPOSIT * 100:.0f}% позиции: "
                f"balance={balance:.2f} USDT, price={price:.2f}, "
                f"нужно {contracts_float:.4f} контрактов"
            )
        return volume

    @classmethod
    async def get_klines(
        cls,
        symbol: TickerEnum,
        period: str,
        size: int,
    ) -> list[KlineSchema]:
        """
        Возвращает свечи от старых к новым (index -1 — последняя закрытая).

        period: "15min", "4hour" и т.п. (в формате HTX).
        """

        logger.info("Загружаем свечи с HTX: %s %s %d", symbol.value, period, size)

        params = {
            "contract_code": ticker_to_htx_code[symbol],
            "period": period,
            "size": size,
        }

        async with httpx.AsyncClient(timeout=HTX_TIMEOUT, verify=False) as client:
            resp = await client.get(HTX_GET_KLINES_API_URL, params=params)
            resp.raise_for_status()
            body = resp.json()

        if body.get("status") != "ok":
            raise RuntimeError(f"Ошибка при загрузке свечей с HTX: {body}")

        raw = list(reversed(body["data"]))
        return [
            KlineSchema(
                open=float(k["open"]),
                high=float(k["high"]),
                low=float(k["low"]),
                close=float(k["close"]),
                volume=float(k["vol"]),
                timestamp=int(k["id"]),
            )
            for k in raw
        ]

    @classmethod
    async def get_margin_balance(cls) -> float:
        """
        Возвращает margin_balance USDT в Unified Account.
        """

        logger.info("Загружаем баланс с HTX")

        data = await cls._signed_post(
            HTX_ACCOUNT_INFO_API_URL,
            HTX_ACCOUNT_INFO_API_PATH,
            {"margin_account": "USDT"},
        )
        accounts = data.get("data") or []
        usdt_account = next(
            (a for a in accounts if a.get("margin_asset") == "USDT"),
            None,
        )
        if usdt_account is None:
            assets = [a.get("margin_asset") for a in accounts]
            raise RuntimeError(
                f"USDT unified-аккаунт не найден в ответе HTX, есть: {assets}"
            )

        balance = float(usdt_account["margin_balance"])
        logger.info("HTX USDT unified margin_balance = %.6f", balance)
        return balance

    @classmethod
    async def place_order(
        cls,
        action: Literal["buy", "sell"],
        symbol: TickerEnum,
        price: float,
        lever_rate: int = DEFAULT_LEVERAGE,
    ) -> dict[str, Any]:
        """
        Открывает позицию маркетом и сразу ставит TP (+3%) и SL (-1%)
        в сторону, выгодную для action.

        action="buy"  -> открыть лонг,  TP = price * 1.03, SL = price * 0.99
        action="sell" -> открыть шорт, TP = price * 0.97, SL = price * 1.01

        Объём позиции — POSITION_PCT (5%) от cross-USDT депозита.
        """

        balance = await cls.get_margin_balance()
        volume = cls._calc_volume(symbol, price, balance, lever_rate)

        if action == "buy":
            tp_price = price * (1 + TAKE_PROFIT)
            sl_price = price * (1 - STOP_LOSS)
        else:
            tp_price = price * (1 - TAKE_PROFIT)
            sl_price = price * (1 + STOP_LOSS)

        logger.info(
            "HTX %s: %s vol=%d price=%.6f -> TP=%.6f SL=%.6f",
            action.upper(),
            ticker_to_htx_code[symbol],
            volume,
            price,
            tp_price,
            sl_price,
        )

        body = {
            "contract_code": ticker_to_htx_code[symbol],
            "volume": volume,
            "direction": action,
            "offset": "open",
            "lever_rate": lever_rate,
            "order_price_type": "opponent",
            "tp_trigger_price": round(tp_price, 4),
            "tp_order_price": round(tp_price, 4),
            "tp_order_price_type": "optimal_5",
            "sl_trigger_price": round(sl_price, 4),
            "sl_order_price": round(sl_price, 4),
            "sl_order_price_type": "optimal_5",
        }
        await cls._signed_post(HTX_ORDER_API_URL, HTX_ORDER_API_PATH, body)

        return body
