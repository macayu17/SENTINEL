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
    simulation_mode: str = os.getenv("SIMULATION_MODE", "SANDBOX")
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


config = Config()
