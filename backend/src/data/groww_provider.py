"""Groww historical candle provider for read-only LIVE_SHADOW replay."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import os
from typing import Any, Dict, Iterable, List, Optional

import numpy as np

from ..market.market_data import StockInfo
from ..utils.config import _reload_environment_values


class GrowwProviderError(RuntimeError):
    """Base error for Groww data-provider failures."""


class GrowwCredentialsError(GrowwProviderError):
    """Raised when server-side Groww credentials are missing."""


class GrowwSdkMissingError(GrowwProviderError):
    """Raised when the optional growwapi SDK is not installed."""


class GrowwDataError(GrowwProviderError):
    """Raised when Groww returns malformed or empty candle data."""


@dataclass(frozen=True)
class GrowwCandle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    oi: Optional[float] = None


@dataclass(frozen=True)
class GrowwQuote:
    groww_symbol: str
    exchange: str
    segment: str
    last_price: float
    ltq: Optional[float] = None
    volume: Optional[float] = None
    previous_close: Optional[float] = None
    timestamp: Optional[str] = None
    total_buy_quantity: Optional[float] = None
    total_sell_quantity: Optional[float] = None
    depth_source: Optional[str] = None
    order_book: Optional[dict[str, list[dict[str, Any]]]] = None


SUPPORTED_SEGMENTS = {"CASH", "FNO"}


INTERVAL_CONSTANTS = {
    "1": "CANDLE_INTERVAL_MIN_1",
    "1M": "CANDLE_INTERVAL_MIN_1",
    "MIN_1": "CANDLE_INTERVAL_MIN_1",
    "2": "CANDLE_INTERVAL_MIN_2",
    "2M": "CANDLE_INTERVAL_MIN_2",
    "MIN_2": "CANDLE_INTERVAL_MIN_2",
    "3": "CANDLE_INTERVAL_MIN_3",
    "3M": "CANDLE_INTERVAL_MIN_3",
    "MIN_3": "CANDLE_INTERVAL_MIN_3",
    "5": "CANDLE_INTERVAL_MIN_5",
    "5M": "CANDLE_INTERVAL_MIN_5",
    "MIN_5": "CANDLE_INTERVAL_MIN_5",
    "10": "CANDLE_INTERVAL_MIN_10",
    "10M": "CANDLE_INTERVAL_MIN_10",
    "MIN_10": "CANDLE_INTERVAL_MIN_10",
    "15": "CANDLE_INTERVAL_MIN_15",
    "15M": "CANDLE_INTERVAL_MIN_15",
    "MIN_15": "CANDLE_INTERVAL_MIN_15",
    "30": "CANDLE_INTERVAL_MIN_30",
    "30M": "CANDLE_INTERVAL_MIN_30",
    "MIN_30": "CANDLE_INTERVAL_MIN_30",
    "60": "CANDLE_INTERVAL_HOUR_1",
    "1H": "CANDLE_INTERVAL_HOUR_1",
    "HOUR_1": "CANDLE_INTERVAL_HOUR_1",
    "240": "CANDLE_INTERVAL_HOUR_4",
    "4H": "CANDLE_INTERVAL_HOUR_4",
    "HOUR_4": "CANDLE_INTERVAL_HOUR_4",
    "1440": "CANDLE_INTERVAL_DAY",
    "1D": "CANDLE_INTERVAL_DAY",
    "DAY_1": "CANDLE_INTERVAL_DAY",
    "10080": "CANDLE_INTERVAL_WEEK",
    "1W": "CANDLE_INTERVAL_WEEK",
    "WEEK_1": "CANDLE_INTERVAL_WEEK",
    "1MO": "CANDLE_INTERVAL_MONTH",
    "MONTH_1": "CANDLE_INTERVAL_MONTH",
}

INTERVAL_BARS_PER_YEAR = {
    "CANDLE_INTERVAL_MIN_1": 252 * (375 / 1),
    "CANDLE_INTERVAL_MIN_2": 252 * (375 / 2),
    "CANDLE_INTERVAL_MIN_3": 252 * (375 / 3),
    "CANDLE_INTERVAL_MIN_5": 252 * (375 / 5),
    "CANDLE_INTERVAL_MIN_10": 252 * (375 / 10),
    "CANDLE_INTERVAL_MIN_15": 252 * (375 / 15),
    "CANDLE_INTERVAL_MIN_30": 252 * (375 / 30),
    "CANDLE_INTERVAL_HOUR_1": 252 * (375 / 60),
    "CANDLE_INTERVAL_HOUR_4": 252 * (375 / 240),
    "CANDLE_INTERVAL_DAY": 252,
    "CANDLE_INTERVAL_WEEK": 52,
    "CANDLE_INTERVAL_MONTH": 12,
}


def normalize_groww_symbol(exchange: str, groww_symbol: str) -> str:
    symbol = groww_symbol.strip().upper()
    if not symbol:
        raise GrowwDataError("Groww symbol is required.")
    exchange_code = exchange.strip().upper() or "NSE"
    if "-" in symbol:
        return symbol
    return f"{exchange_code}-{symbol}"


def normalize_groww_candles(payload: Any) -> List[GrowwCandle]:
    candles = payload.get("candles") if isinstance(payload, dict) else payload
    if not isinstance(candles, list) or not candles:
        raise GrowwDataError("Groww returned no historical candles.")

    normalized: List[GrowwCandle] = []
    for row in candles:
        if isinstance(row, dict):
            normalized.append(
                GrowwCandle(
                    timestamp=_normalize_timestamp(row.get("timestamp") or row.get("time")),
                    open=_finite_float(row.get("open"), "open"),
                    high=_finite_float(row.get("high"), "high"),
                    low=_finite_float(row.get("low"), "low"),
                    close=_finite_float(row.get("close"), "close"),
                    volume=_finite_float(row.get("volume", 0), "volume"),
                    oi=_optional_float(row.get("oi") if "oi" in row else row.get("open_interest")),
                )
            )
            continue

        if not isinstance(row, (list, tuple)) or len(row) < 6:
            raise GrowwDataError("Groww candle rows must include timestamp, OHLC, and volume.")

        normalized.append(
            GrowwCandle(
                timestamp=_normalize_timestamp(row[0]),
                open=_finite_float(row[1], "open"),
                high=_finite_float(row[2], "high"),
                low=_finite_float(row[3], "low"),
                close=_finite_float(row[4], "close"),
                volume=_finite_float(row[5], "volume"),
                oi=_optional_float(row[6] if len(row) > 6 else None),
            )
        )

    return normalized


def normalize_groww_quote(
    payload: Any,
    *,
    exchange: str,
    segment: str,
    groww_symbol: str,
) -> GrowwQuote:
    if not isinstance(payload, dict):
        raise GrowwDataError("Groww quote response was not a JSON object.")

    symbol = normalize_groww_symbol(exchange, groww_symbol)
    depth = payload.get("depth") if isinstance(payload.get("depth"), dict) else {}
    bids = _normalize_depth_side(depth.get("buy"), "bid")
    asks = _normalize_depth_side(depth.get("sell"), "ask")
    ohlc = payload.get("ohlc") if isinstance(payload.get("ohlc"), dict) else {}

    return GrowwQuote(
        groww_symbol=symbol,
        exchange=exchange.strip().upper() or "NSE",
        segment=segment.strip().upper() or "CASH",
        last_price=_finite_float(payload.get("last_price"), "quote last price"),
        ltq=_optional_float(payload.get("last_trade_quantity")),
        volume=_optional_float(payload.get("volume")),
        previous_close=_optional_float(ohlc.get("close")),
        timestamp=str(payload.get("last_trade_time")).strip() if payload.get("last_trade_time") is not None else None,
        total_buy_quantity=_optional_float(payload.get("total_buy_quantity")),
        total_sell_quantity=_optional_float(payload.get("total_sell_quantity")),
        depth_source="provider_live" if bids or asks else None,
        order_book={"bids": bids, "asks": asks} if bids or asks else None,
    )


def groww_candles_to_stock_info(
    groww_symbol: str,
    candles: Iterable[GrowwCandle],
    exchange: str,
    segment: str,
    candle_interval: str = "DAY_1",
) -> StockInfo:
    candle_list = list(candles)
    if len(candle_list) < 2:
        raise GrowwDataError("Groww replay requires at least two candles.")

    closes = [c.close for c in candle_list]
    highs = [c.high for c in candle_list]
    lows = [c.low for c in candle_list]
    volumes = [c.volume for c in candle_list]
    log_returns = [
        float(math.log(closes[i] / closes[i - 1]))
        for i in range(1, len(closes))
        if closes[i] > 0 and closes[i - 1] > 0
    ]
    std = float(np.std(log_returns)) if log_returns else 0.01
    realized_vol = std * float(np.sqrt(_bars_per_year_for_interval(candle_interval)))
    mean_return = float(np.mean(log_returns)) if log_returns else 0.0
    symbol = normalize_groww_symbol(exchange, groww_symbol)
    segment_code = segment.strip().upper() or "CASH"

    return StockInfo(
        ticker=symbol,
        name=f"{symbol} Groww {segment_code}",
        currency="INR",
        last_close=float(closes[-1]),
        period_start=candle_list[0].timestamp,
        period_end=candle_list[-1].timestamp,
        bars=len(candle_list),
        prices=closes,
        volumes=volumes,
        highs=highs,
        lows=lows,
        returns=log_returns,
        realized_vol=round(realized_vol, 4),
        mean_return=round(mean_return, 6),
    )


class GrowwHistoricalProvider:
    """Thin SDK wrapper that keeps Groww credentials server-side."""

    def __init__(self, auth_token: Optional[str] = None, client: Optional[Any] = None) -> None:
        self._client = client
        if self._client is not None:
            return

        _reload_environment_values(
            [
                "GROWW_API_AUTH_TOKEN",
                "GROWW_API_KEY",
                "GROWW_API_SECRET",
                "GROWW_API_TOTP",
            ]
        )
        token = auth_token or os.getenv("GROWW_API_AUTH_TOKEN")
        api_key = os.getenv("GROWW_API_KEY")
        api_secret = os.getenv("GROWW_API_SECRET")
        if not token and not (api_key and api_secret):
            raise GrowwCredentialsError(
                "Groww credentials missing. Set GROWW_API_AUTH_TOKEN or GROWW_API_KEY/GROWW_API_SECRET in backend/.env."
            )

        try:
            from growwapi import GrowwAPI
        except ImportError as exc:
            raise GrowwSdkMissingError("growwapi is not installed. Run: pip install growwapi") from exc

        if not token:
            try:
                token = GrowwAPI.get_access_token(
                    api_key=api_key,
                    secret=api_secret,
                    totp=os.getenv("GROWW_API_TOTP") or None,
                )
            except Exception as exc:
                raise GrowwCredentialsError(
                    "Groww access-token request was rejected. Check GROWW_API_KEY/GROWW_API_SECRET or use GROWW_API_AUTH_TOKEN."
                ) from exc
        self._client = GrowwAPI(token)

    def fetch_historical(
        self,
        *,
        exchange: str,
        segment: str,
        groww_symbol: str,
        start_time: str,
        end_time: str,
        candle_interval: str = "MIN_30",
    ) -> StockInfo:
        segment_code = segment.strip().upper() or "CASH"
        if segment_code not in SUPPORTED_SEGMENTS:
            supported = ", ".join(sorted(SUPPORTED_SEGMENTS))
            raise GrowwDataError(f"Unsupported Groww segment '{segment}'. Supported: {supported}.")

        symbol = normalize_groww_symbol(exchange, groww_symbol)
        exchange_value = _client_constant(self._client, f"EXCHANGE_{exchange.strip().upper()}", exchange.strip().upper())
        segment_value = _client_constant(self._client, f"SEGMENT_{segment_code}", segment_code)
        interval_value = _resolve_interval_constant(self._client, candle_interval)

        try:
            response = self._client.get_historical_candles(
                exchange=exchange_value,
                segment=segment_value,
                groww_symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                candle_interval=interval_value,
            )
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            if "forbidden" in message.lower() or "access" in message.lower():
                raise GrowwDataError(
                    "Groww rejected historical candle access. Verify this Groww API key has historical/backtesting data permission."
                ) from exc
            raise GrowwProviderError(f"Groww historical candle request failed: {message}") from exc
        candles = normalize_groww_candles(response)
        return groww_candles_to_stock_info(
            groww_symbol=symbol,
            candles=candles,
            exchange=exchange,
            segment=segment_code,
            candle_interval=candle_interval,
        )

    def fetch_quote(
        self,
        *,
        exchange: str,
        segment: str,
        groww_symbol: str,
    ) -> GrowwQuote:
        segment_code = segment.strip().upper() or "CASH"
        if segment_code not in SUPPORTED_SEGMENTS:
            supported = ", ".join(sorted(SUPPORTED_SEGMENTS))
            raise GrowwDataError(f"Unsupported Groww segment '{segment}'. Supported: {supported}.")

        symbol = normalize_groww_symbol(exchange, groww_symbol)
        exchange_code = exchange.strip().upper() or "NSE"
        exchange_value = _client_constant(self._client, f"EXCHANGE_{exchange_code}", exchange_code)
        segment_value = _client_constant(self._client, f"SEGMENT_{segment_code}", segment_code)
        trading_symbol = _quote_trading_symbol(exchange_code, symbol)

        try:
            response = self._client.get_quote(
                exchange=exchange_value,
                segment=segment_value,
                trading_symbol=trading_symbol,
            )
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            if "forbidden" in message.lower() or "access" in message.lower():
                raise GrowwDataError(
                    "Groww rejected live quote access. Verify this Groww API key has live data permission."
                ) from exc
            raise GrowwProviderError(f"Groww live quote request failed: {message}") from exc

        return normalize_groww_quote(
            response,
            exchange=exchange_code,
            segment=segment_code,
            groww_symbol=symbol,
        )


def fetch_groww_historical_stock(
    *,
    exchange: str,
    segment: str,
    groww_symbol: str,
    start_time: str,
    end_time: str,
    candle_interval: str = "MIN_30",
    provider: Optional[GrowwHistoricalProvider] = None,
) -> StockInfo:
    active_provider = provider or GrowwHistoricalProvider()
    return active_provider.fetch_historical(
        exchange=exchange,
        segment=segment,
        groww_symbol=groww_symbol,
        start_time=start_time,
        end_time=end_time,
        candle_interval=candle_interval,
    )


def fetch_groww_quote(
    *,
    exchange: str,
    segment: str,
    groww_symbol: str,
    provider: Optional[GrowwHistoricalProvider] = None,
) -> GrowwQuote:
    active_provider = provider or GrowwHistoricalProvider()
    return active_provider.fetch_quote(
        exchange=exchange,
        segment=segment,
        groww_symbol=groww_symbol,
    )


def _normalize_timestamp(value: Any) -> str:
    if value is None:
        raise GrowwDataError("Groww candle timestamp is missing.")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None).isoformat()
    return str(value)


def _finite_float(value: Any, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise GrowwDataError(f"Groww candle {field} is not numeric.") from exc
    if not math.isfinite(parsed):
        raise GrowwDataError(f"Groww candle {field} is not finite.")
    return parsed


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return _finite_float(value, "open interest")


def _normalize_depth_side(entries: Any, side: str) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        return []

    levels: list[dict[str, Any]] = []
    for row in entries:
        if not isinstance(row, dict):
            continue
        try:
            price = _finite_float(row.get("price"), f"{side} depth price")
            size = int(_finite_float(row.get("quantity", row.get("qty")), f"{side} depth quantity"))
        except GrowwDataError:
            continue
        if price <= 0 or size <= 0:
            continue
        levels.append({"price": round(price, 2), "size": size})

    return sorted(levels, key=lambda level: level["price"], reverse=(side == "bid"))


def _quote_trading_symbol(exchange: str, groww_symbol: str) -> str:
    prefix = f"{exchange.strip().upper()}-"
    if groww_symbol.upper().startswith(prefix):
        return groww_symbol[len(prefix):]
    return groww_symbol


def _client_constant(client: Any, name: str, fallback: str) -> Any:
    return getattr(client, name, getattr(client.__class__, name, fallback))


def _resolve_interval_constant(client: Any, interval: str) -> Any:
    constant_name = _normalize_interval_constant_name(interval)
    return _client_constant(client, constant_name, constant_name)


def _bars_per_year_for_interval(interval: str) -> float:
    constant_name = _normalize_interval_constant_name(interval)
    return INTERVAL_BARS_PER_YEAR.get(constant_name, 252)


def _normalize_interval_constant_name(interval: str) -> str:
    code = str(interval).strip().upper().replace(" ", "_").replace("-", "_")
    if code.startswith("CANDLE_INTERVAL_"):
        return code
    return INTERVAL_CONSTANTS.get(code, f"CANDLE_INTERVAL_{code}")
