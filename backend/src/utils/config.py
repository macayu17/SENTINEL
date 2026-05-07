"""Configuration for the SENTINEL market simulator."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_UTILS_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _UTILS_DIR.parents[1]
_PROJECT_ROOT = _UTILS_DIR.parents[2]


def _split_csv(value: str) -> list[str]:
    return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _resolve_repo_path(value: str) -> str:
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)

    candidates = [
        Path.cwd() / path,
        _BACKEND_ROOT / path,
        _PROJECT_ROOT / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())

    return str((_BACKEND_ROOT / path).resolve())


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

    # RL policy
    rl_policy_enabled: bool = _get_bool("RL_POLICY_ENABLED", False)
    rl_policy_kind: str = os.getenv("RL_POLICY_KIND", "ppo").strip().lower()
    rl_model_path: str = _resolve_repo_path(
        os.getenv("RL_MODEL_PATH", os.path.join("models", "ppo_market_maker.zip"))
    )


config = Config()
