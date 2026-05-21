"""Upstox market-data provider for read-only LIVE_SHADOW replay."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import os
from typing import Any, Iterable, List, Optional
from urllib.parse import quote

import httpx
import numpy as np

from ..market.market_data import StockInfo


class UpstoxProviderError(RuntimeError):
    """Base error for Upstox data-provider failures."""


class UpstoxCredentialsError(UpstoxProviderError):
    """Raised when server-side Upstox credentials are missing or rejected."""


class UpstoxDataError(UpstoxProviderError, ValueError):
    """Raised when Upstox returns malformed or unsupported candle data."""


@dataclass(frozen=True)
class UpstoxCandle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    oi: Optional[float] = None


@dataclass(frozen=True)
class UpstoxInstrument:
    instrument_key: str
    trading_symbol: str
    name: str
    exchange: str
    segment: str
    instrument_type: str
    isin: Optional[str] = None
    short_name: Optional[str] = None


@dataclass(frozen=True)
class UpstoxQuote:
    instrument_key: str
    last_price: float
    ltq: Optional[float] = None
    volume: Optional[float] = None
    previous_close: Optional[float] = None


SUPPORTED_UNITS = {"minutes", "hours", "days", "weeks", "months"}


def normalize_upstox_instrument_key(instrument_key: str) -> str:
    key = instrument_key.strip()
    if not key:
        raise UpstoxDataError("Upstox instrument_key is required.")
    return key


def validate_upstox_interval(unit: str, interval: str) -> None:
    unit_code = unit.strip().lower()
    interval_code = str(interval).strip()
    if unit_code not in SUPPORTED_UNITS:
        supported = ", ".join(sorted(SUPPORTED_UNITS))
        raise UpstoxDataError(f"Unsupported Upstox unit '{unit}'. Supported: {supported}.")

    try:
        interval_value = int(interval_code)
    except ValueError as exc:
        raise UpstoxDataError("Upstox interval must be numeric.") from exc

    if unit_code == "minutes" and 1 <= interval_value <= 300:
        return
    if unit_code == "hours" and 1 <= interval_value <= 5:
        return
    if unit_code in {"days", "weeks", "months"} and interval_value == 1:
        return

    raise UpstoxDataError(f"Unsupported Upstox interval '{interval}' for unit '{unit_code}'.")


def normalize_upstox_candles(payload: Any) -> List[UpstoxCandle]:
    if isinstance(payload, dict):
        status = payload.get("status")
        if status and status != "success":
            raise UpstoxDataError(_upstox_error_message(payload))
        data = payload.get("data")
        candles = data.get("candles") if isinstance(data, dict) else payload.get("candles")
    else:
        candles = payload

    if not isinstance(candles, list) or not candles:
        raise UpstoxDataError("Upstox returned no historical candles.")

    normalized: List[UpstoxCandle] = []
    for row in candles:
        if isinstance(row, dict):
            normalized.append(
                UpstoxCandle(
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
            raise UpstoxDataError("Upstox candle rows must include timestamp, OHLC, and volume.")

        normalized.append(
            UpstoxCandle(
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


def normalize_upstox_instruments(payload: Any) -> List[UpstoxInstrument]:
    if not isinstance(payload, dict):
        raise UpstoxDataError("Upstox instrument search returned a non-object response.")

    status = payload.get("status")
    if status and status != "success":
        raise UpstoxDataError(_upstox_error_message(payload))

    rows = payload.get("data")
    if rows is None:
        rows = payload.get("instruments")
    if not isinstance(rows, list):
        raise UpstoxDataError("Upstox instrument search returned no result list.")

    instruments: List[UpstoxInstrument] = []
    for row in rows:
        if not isinstance(row, dict):
            raise UpstoxDataError("Upstox instrument rows must be objects.")

        instrument_key = str(row.get("instrument_key") or "").strip()
        if not instrument_key:
            raise UpstoxDataError("Upstox instrument row is missing instrument_key.")

        trading_symbol = str(
            row.get("trading_symbol")
            or row.get("tradingsymbol")
            or row.get("symbol")
            or ""
        ).strip()
        name = str(row.get("name") or row.get("company_name") or trading_symbol or instrument_key).strip()
        exchange = str(row.get("exchange") or "").strip()
        segment = str(row.get("segment") or "").strip()
        instrument_type = str(row.get("instrument_type") or row.get("instrumentType") or "").strip()
        isin = row.get("isin")
        short_name = row.get("short_name")

        instruments.append(
            UpstoxInstrument(
                instrument_key=instrument_key,
                trading_symbol=trading_symbol,
                name=name,
                exchange=exchange,
                segment=segment,
                instrument_type=instrument_type,
                isin=str(isin).strip() if isin else None,
                short_name=str(short_name).strip() if short_name else None,
            )
        )

    return instruments


def normalize_upstox_ltp(payload: Any, instrument_key: str) -> UpstoxQuote:
    key = normalize_upstox_instrument_key(instrument_key)
    if not isinstance(payload, dict):
        raise UpstoxDataError("Upstox LTP response was not a JSON object.")

    status = payload.get("status")
    if status and status != "success":
        raise UpstoxDataError(_upstox_error_message(payload))

    data = payload.get("data")
    if not isinstance(data, dict) or not data:
        raise UpstoxDataError("Upstox returned no LTP quote data.")

    selected = None
    for quote in data.values():
        if not isinstance(quote, dict):
            continue
        token = str(quote.get("instrument_token") or quote.get("instrument_key") or "").strip()
        if token == key:
            selected = quote
            break
        if selected is None:
            selected = quote

    if selected is None:
        raise UpstoxDataError("Upstox LTP response did not include a usable quote.")

    token = str(selected.get("instrument_token") or selected.get("instrument_key") or key).strip() or key
    return UpstoxQuote(
        instrument_key=token,
        last_price=_finite_float(selected.get("last_price"), "last price"),
        ltq=_optional_float(selected.get("ltq"), "ltq"),
        volume=_optional_float(selected.get("volume"), "volume"),
        previous_close=_optional_float(
            selected.get("cp") if "cp" in selected else selected.get("previous_close"),
            "previous close",
        ),
    )


def upstox_candles_to_stock_info(
    instrument_key: str,
    candles: Iterable[UpstoxCandle],
    unit: str,
    interval: str,
) -> StockInfo:
    candle_list = list(candles)
    if len(candle_list) < 2:
        raise UpstoxDataError("Upstox replay requires at least two candles.")

    key = normalize_upstox_instrument_key(instrument_key)
    unit_code = unit.strip().lower()
    interval_code = str(interval).strip()
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
    realized_vol = std * float(np.sqrt(_bars_per_year(unit_code, interval_code)))
    mean_return = float(np.mean(log_returns)) if log_returns else 0.0

    return StockInfo(
        ticker=key,
        name=f"{key} Upstox {unit_code}/{interval_code}",
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


class UpstoxHistoricalProvider:
    """REST wrapper that keeps Upstox tokens server-side."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        base_url: Optional[str] = None,
        v2_base_url: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
        timeout: float = 10.0,
    ) -> None:
        token = access_token or os.getenv("UPSTOX_ACCESS_TOKEN") or os.getenv("UPSTOX_ANALYTICS_TOKEN")
        if not token:
            raise UpstoxCredentialsError(
                "Upstox credentials missing. Set UPSTOX_ACCESS_TOKEN or UPSTOX_ANALYTICS_TOKEN in backend/.env."
            )

        self._token = token
        self._base_url = (base_url or os.getenv("UPSTOX_BASE_URL") or "https://api.upstox.com/v3").rstrip("/")
        self._v2_base_url = (
            v2_base_url or os.getenv("UPSTOX_V2_BASE_URL") or "https://api.upstox.com/v2"
        ).rstrip("/")
        self._client = http_client or httpx.Client(timeout=timeout)

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
        }

    def fetch_historical(
        self,
        *,
        instrument_key: str,
        unit: str,
        interval: str,
        to_date: str,
        from_date: Optional[str] = None,
    ) -> StockInfo:
        key = normalize_upstox_instrument_key(instrument_key)
        unit_code = unit.strip().lower()
        interval_code = str(interval).strip()
        validate_upstox_interval(unit_code, interval_code)
        _validate_date_range(from_date=from_date, to_date=to_date)

        encoded_key = quote(key, safe="")
        url = f"{self._base_url}/historical-candle/{encoded_key}/{unit_code}/{interval_code}/{to_date.strip()}"
        if from_date:
            url = f"{url}/{from_date.strip()}"

        try:
            response = self._client.get(
                url,
                headers=self._headers(),
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in {401, 403}:
                raise UpstoxCredentialsError(
                    f"Upstox rejected historical candle access ({status}). Check UPSTOX_ACCESS_TOKEN/UPSTOX_ANALYTICS_TOKEN and market-data permissions."
                ) from exc
            raise UpstoxProviderError(f"Upstox historical candle request failed ({status}): {exc.response.text}") from exc
        except httpx.RequestError as exc:
            raise UpstoxProviderError(f"Upstox historical candle request failed: {exc}") from exc
        except ValueError as exc:
            raise UpstoxDataError("Upstox returned a non-JSON historical candle response.") from exc

        candles = normalize_upstox_candles(payload)
        return upstox_candles_to_stock_info(
            instrument_key=key,
            candles=candles,
            unit=unit_code,
            interval=interval_code,
        )

    def search_instruments(
        self,
        *,
        query: str,
        exchanges: str = "NSE",
        segments: str = "EQ",
        page_number: int = 1,
        records: int = 10,
    ) -> List[UpstoxInstrument]:
        query_text = query.strip()
        if not query_text:
            raise UpstoxDataError("Upstox instrument search query is required.")
        if len(query_text) > 50:
            raise UpstoxDataError("Upstox instrument search query must be 50 characters or less.")

        page = max(1, int(page_number))
        record_count = min(30, max(1, int(records)))
        params: dict[str, Any] = {
            "query": query_text,
            "page_number": page,
            "records": record_count,
        }
        if exchanges.strip():
            params["exchanges"] = exchanges.strip().upper()
        if segments.strip():
            params["segments"] = segments.strip().upper()

        try:
            response = self._client.get(
                f"{self._v2_base_url}/instruments/search",
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in {401, 403}:
                raise UpstoxCredentialsError(
                    f"Upstox rejected instrument-search access ({status}). Check UPSTOX_ACCESS_TOKEN/UPSTOX_ANALYTICS_TOKEN and market-data permissions."
                ) from exc
            raise UpstoxProviderError(f"Upstox instrument search failed ({status}): {exc.response.text}") from exc
        except httpx.RequestError as exc:
            raise UpstoxProviderError(f"Upstox instrument search failed: {exc}") from exc
        except ValueError as exc:
            raise UpstoxDataError("Upstox returned a non-JSON instrument-search response.") from exc

        return normalize_upstox_instruments(payload)

    def fetch_ltp(self, *, instrument_key: str) -> UpstoxQuote:
        key = normalize_upstox_instrument_key(instrument_key)
        try:
            response = self._client.get(
                f"{self._base_url}/market-quote/ltp",
                headers=self._headers(),
                params={"instrument_key": key},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in {401, 403}:
                raise UpstoxCredentialsError(
                    f"Upstox rejected LTP quote access ({status}). Check UPSTOX_ACCESS_TOKEN/UPSTOX_ANALYTICS_TOKEN and market-data permissions."
                ) from exc
            raise UpstoxProviderError(f"Upstox LTP quote request failed ({status}): {exc.response.text}") from exc
        except httpx.RequestError as exc:
            raise UpstoxProviderError(f"Upstox LTP quote request failed: {exc}") from exc
        except ValueError as exc:
            raise UpstoxDataError("Upstox returned a non-JSON LTP quote response.") from exc

        return normalize_upstox_ltp(payload, key)


def fetch_upstox_historical_stock(
    *,
    instrument_key: str,
    unit: str,
    interval: str,
    to_date: str,
    from_date: Optional[str] = None,
    provider: Optional[UpstoxHistoricalProvider] = None,
) -> StockInfo:
    active_provider = provider or UpstoxHistoricalProvider()
    return active_provider.fetch_historical(
        instrument_key=instrument_key,
        unit=unit,
        interval=interval,
        to_date=to_date,
        from_date=from_date,
    )


def search_upstox_instruments(
    *,
    query: str,
    exchanges: str = "NSE",
    segments: str = "EQ",
    page_number: int = 1,
    records: int = 10,
    provider: Optional[UpstoxHistoricalProvider] = None,
) -> List[UpstoxInstrument]:
    active_provider = provider or UpstoxHistoricalProvider()
    return active_provider.search_instruments(
        query=query,
        exchanges=exchanges,
        segments=segments,
        page_number=page_number,
        records=records,
    )


def fetch_upstox_ltp_quote(
    *,
    instrument_key: str,
    provider: Optional[UpstoxHistoricalProvider] = None,
) -> UpstoxQuote:
    active_provider = provider or UpstoxHistoricalProvider()
    return active_provider.fetch_ltp(instrument_key=instrument_key)


def _validate_date_range(*, from_date: Optional[str], to_date: str) -> None:
    to_dt = _parse_date(to_date, "to_date")
    if from_date:
        from_dt = _parse_date(from_date, "from_date")
        if to_dt < from_dt:
            raise UpstoxDataError("Upstox to_date must be greater than or equal to from_date.")


def _parse_date(value: str, field: str) -> datetime:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d")
    except (AttributeError, ValueError) as exc:
        raise UpstoxDataError(f"Upstox {field} must use YYYY-MM-DD format.") from exc


def _normalize_timestamp(value: Any) -> str:
    if value is None:
        raise UpstoxDataError("Upstox candle timestamp is missing.")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None).isoformat()
    return str(value)


def _finite_float(value: Any, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise UpstoxDataError(f"Upstox {field} is not numeric.") from exc
    if not math.isfinite(parsed):
        raise UpstoxDataError(f"Upstox {field} is not finite.")
    return parsed


def _optional_float(value: Any, field: str = "open interest") -> Optional[float]:
    if value is None:
        return None
    return _finite_float(value, field)


def _bars_per_year(unit: str, interval: str) -> float:
    interval_value = max(1, int(interval))
    if unit == "minutes":
        return 252 * (375 / interval_value)
    if unit == "hours":
        return 252 * (6.25 / interval_value)
    if unit == "weeks":
        return 52
    if unit == "months":
        return 12
    return 252


def _upstox_error_message(payload: dict) -> str:
    if isinstance(payload.get("message"), str):
        return payload["message"]
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            return str(first.get("message") or first.get("errorCode") or first)
        return str(first)
    return "Upstox historical candle request was rejected."
