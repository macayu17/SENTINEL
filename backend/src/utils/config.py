"""Configuration for the SENTINEL market simulator."""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Global configuration loaded from environment variables."""

    # Simulation
    simulation_mode: str = os.getenv("SIMULATION_MODE", "SANDBOX")
    initial_price: float = float(os.getenv("INITIAL_PRICE", "100.0"))
    simulation_duration: int = int(os.getenv("SIMULATION_DURATION", "23400"))

    # Stitch MCP
    stitch_api_key: str = os.getenv("STITCH_API_KEY", "")
    stitch_base_url: str = os.getenv("STITCH_BASE_URL", "https://api.stitch.money/mcp")
    stitch_symbol: str = os.getenv("STITCH_SYMBOL", "AAPL")

    # Server
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    # Feature baselines
    baseline_spread: float = 0.001
    baseline_depth: float = 1000.0
    baseline_volatility: float = 0.02


config = Config()
