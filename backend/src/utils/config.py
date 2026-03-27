"""Configuration for the SENTINEL market simulator."""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _split_csv(value: str) -> list[str]:
    return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]


def _default_allowed_origins() -> list[str]:
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    frontend_url = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
    if frontend_url:
        origins.append(frontend_url)

    origins.extend(_split_csv(os.getenv("ALLOWED_ORIGINS", "")))

    deduped: list[str] = []
    for origin in origins:
        if origin not in deduped:
            deduped.append(origin)
    return deduped


@dataclass
class Config:
    """Global configuration loaded from environment variables."""

    # Simulation
    simulation_mode: str = os.getenv("SIMULATION_MODE", "SIMULATION")
    initial_price: float = float(os.getenv("INITIAL_PRICE", "100.0"))
    simulation_duration: int = int(os.getenv("SIMULATION_DURATION", "23400"))

    # Server
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    allowed_origins: list[str] = field(default_factory=_default_allowed_origins)

    # Feature baselines
    baseline_spread: float = 0.001
    baseline_depth: float = 1000.0
    baseline_volatility: float = 0.02

    # Live-feed integration
    live_feed_provider: str = os.getenv("LIVE_FEED_PROVIDER", "binance").strip().lower()
    live_feed_symbol: str = os.getenv("LIVE_FEED_SYMBOL", "btcusdt").strip().lower()
    live_feed_reconnect_base: float = float(os.getenv("LIVE_FEED_RECONNECT_BASE", "1.0"))
    live_feed_reconnect_max: float = float(os.getenv("LIVE_FEED_RECONNECT_MAX", "20.0"))
    live_feed_poll_interval_seconds: float = float(os.getenv("LIVE_FEED_POLL_INTERVAL_SECONDS", "1.0"))
    live_feed_stale_after_seconds: float = float(os.getenv("LIVE_FEED_STALE_AFTER_SECONDS", "6.0"))

    # Broker/exchange integration
    broker_stream_mode: str = os.getenv("BROKER_STREAM_MODE", "auto").strip().lower()
    broker_ws_url: str = os.getenv("BROKER_WS_URL", "").strip()
    broker_rest_url: str = os.getenv("BROKER_REST_URL", "").strip()
    broker_api_key: str = os.getenv("BROKER_API_KEY", "").strip()
    broker_api_secret: str = os.getenv("BROKER_API_SECRET", "").strip()
    broker_access_token: str = os.getenv("BROKER_ACCESS_TOKEN", "").strip()
    broker_account_id: str = os.getenv("BROKER_ACCOUNT_ID", "").strip()

    def validate(self) -> None:
        supported = {"binance", "nse", "mock", "broker", "scraper"}
        if self.live_feed_provider not in supported:
            raise ValueError(
                f"Unsupported LIVE_FEED_PROVIDER='{self.live_feed_provider}'. "
                f"Use one of: {', '.join(sorted(supported))}."
            )

        if self.live_feed_poll_interval_seconds <= 0:
            raise ValueError("LIVE_FEED_POLL_INTERVAL_SECONDS must be > 0.")
        if self.live_feed_stale_after_seconds <= 0:
            raise ValueError("LIVE_FEED_STALE_AFTER_SECONDS must be > 0.")

        if self.live_feed_provider == "broker":
            self._validate_broker_settings()

    def _validate_broker_settings(self) -> None:
        mode = self.broker_stream_mode
        if mode not in {"auto", "stream", "poll"}:
            raise ValueError("BROKER_STREAM_MODE must be one of: auto, stream, poll.")

        if not (self.broker_api_key or self.broker_access_token):
            raise ValueError(
                "Broker authentication missing. Set BROKER_API_KEY or BROKER_ACCESS_TOKEN."
            )

        if mode == "stream" and not self.broker_ws_url:
            raise ValueError("BROKER_WS_URL is required when BROKER_STREAM_MODE=stream.")
        if mode == "poll" and not self.broker_rest_url:
            raise ValueError("BROKER_REST_URL is required when BROKER_STREAM_MODE=poll.")
        if mode == "auto" and not (self.broker_ws_url or self.broker_rest_url):
            raise ValueError(
                "BROKER_STREAM_MODE=auto requires BROKER_WS_URL or BROKER_REST_URL."
            )


config = Config()
