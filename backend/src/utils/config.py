"""Configuration for the SENTINEL market simulator."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import dotenv_values, load_dotenv

_UTILS_DIR = Path(__file__).resolve().parent
_BACKEND_ROOT = _UTILS_DIR.parents[1]
_PROJECT_ROOT = _UTILS_DIR.parents[2]


def _load_environment_files(backend_root: Path = _BACKEND_ROOT, project_root: Path = _PROJECT_ROOT) -> None:
    """Load dotenv files from stable repo locations, independent of cwd."""
    for env_file in (backend_root / ".env", project_root / ".env"):
        if env_file.exists():
            load_dotenv(env_file, override=False)


_load_environment_files()


def _reload_environment_values(
    names: list[str],
    backend_root: Path = _BACKEND_ROOT,
    project_root: Path = _PROJECT_ROOT,
) -> None:
    """Fill missing runtime env values from dotenv without overriding real env."""
    pending = [name for name in names if not os.getenv(name)]
    if not pending:
        return

    for env_file in (backend_root / ".env", project_root / ".env"):
        if not env_file.exists():
            continue
        values = dotenv_values(env_file)
        for name in list(pending):
            value = values.get(name)
            if value:
                os.environ[name] = value
                pending.remove(name)
        if not pending:
            return


def _split_csv(value: str) -> list[str]:
    return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]


def _default_allowed_origins() -> list[str]:
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
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
