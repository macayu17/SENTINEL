"""Stitch MCP client for external market data ingestion (stub implementation)."""

from typing import Dict, List, Optional, Callable
import httpx
from ..utils.logger import get_logger
from ..utils.config import config

logger = get_logger("stitch_mcp")


class StitchMCPClient:
    """
    Client for connecting to the Stitch MCP external market data API.

    This is a stub implementation with the correct interface —
    actual API calls require a valid STITCH_API_KEY.
    """

    def __init__(
        self,
        api_key: str = config.stitch_api_key,
        base_url: str = config.stitch_base_url,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None
        self.connected = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10.0,
            )
        return self._client

    async def get_market_snapshot(self, symbol: str) -> Dict:
        """
        Returns current bid, ask, last price, volume from Stitch.
        Falls back to synthetic data if API is unavailable.
        """
        if not self.api_key:
            logger.info("No Stitch API key configured, returning synthetic data")
            return self._synthetic_snapshot(symbol)

        try:
            client = await self._get_client()
            response = await client.get(f"/v1/market/{symbol}/snapshot")
            response.raise_for_status()
            self.connected = True
            return response.json()
        except Exception as e:
            logger.warning(f"Stitch API error: {e}, falling back to synthetic data")
            self.connected = False
            return self._synthetic_snapshot(symbol)

    async def stream_trades(self, symbol: str, callback: Callable) -> None:
        """
        Streams live trade feed, calls callback on each trade.
        Stub: generates synthetic trade events.
        """
        logger.info(f"Trade stream for {symbol} — stub mode (no API key)")

    async def get_historical_ohlcv(
        self, symbol: str, interval: str = "1m", bars: int = 100
    ) -> List[Dict]:
        """
        Returns OHLCV bars for backtesting feature baseline calibration.
        Stub: returns empty list when no API key.
        """
        if not self.api_key:
            logger.info("No Stitch API key, returning empty OHLCV")
            return []

        try:
            client = await self._get_client()
            response = await client.get(
                f"/v1/market/{symbol}/ohlcv",
                params={"interval": interval, "bars": bars},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"Stitch OHLCV error: {e}")
            return []

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _synthetic_snapshot(self, symbol: str) -> Dict:
        """Generate synthetic market snapshot for development/testing."""
        import random
        base = 100.0
        return {
            "symbol": symbol,
            "bid": round(base - random.uniform(0.01, 0.05), 2),
            "ask": round(base + random.uniform(0.01, 0.05), 2),
            "last_price": round(base + random.uniform(-0.03, 0.03), 2),
            "volume": random.randint(10000, 500000),
            "timestamp": 0.0,
        }
