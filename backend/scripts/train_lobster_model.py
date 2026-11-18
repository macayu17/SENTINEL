#!/usr/bin/env python3
"""Train the liquidity-shock model on NASDAQ LOBSTER days plus simulator runs.

Recipe (chosen by leave-one-ticker-out comparison of logistic regression,
random forest, HistGradientBoosting, XGBoost, four LightGBM configurations
and rank ensembles):

- 32 scale-free features from the shared LiquidityFeatureTracker, 1 s grid
  (short-term book state, 5-15 min memory, 10-level book shape);
- label: spread >= 2.5x or depth <= 40% of baseline within the next 60 s;
- a small LightGBM (7 leaves, lr 0.02, L2 20, 2,000 rounds, picked by random
  search) on all LOBSTER days, with 28 simulator runs weighted to 25% of the
  data (domain adaptation);
- isotonic calibration and the F1 threshold on the last 20% of every day/run.

The report carries held-out scores: each ticker scored by a model that never saw
it, each simulator run by a model trained without it.
"""

from __future__ import annotations

import argparse
import json
from math import sqrt
from multiprocessing import Pool
from pathlib import Path
import pickle

import numpy as np

try:
    from _path_setup import BACKEND_ROOT, add_repo_root_to_path
except ModuleNotFoundError:
    from backend.scripts._path_setup import BACKEND_ROOT, add_repo_root_to_path

add_repo_root_to_path()

from backend.src.prediction.liquidity_features import FEATURE_NAMES, observation_from_state
from backend.src.prediction.lobster_training import (
    build_samples,
    grid_observations,
    load_day,
    select_probability_threshold,
)

PARAMS = {
    "objective": "binary", "learning_rate": 0.02, "num_leaves": 7, "min_data_in_leaf": 400,
    "bagging_fraction": 0.7, "bagging_freq": 1, "feature_fraction": 0.7, "lambda_l2": 20.0,
    "verbose": -1, "seed": 0, "num_threads": 8,
}
ROUNDS = 2_000
MIN_EVAL_POSITIVES = 20
_SCENARIOS = ("liquidity_shock", "normal", "volatility_spike", "market_open",
              "spoofing_stress", "close_auction", "institutional_execution")
_PRESETS = ("balanced", "institutional", "stress_test")
# Every scenario under every preset (normal: balanced/institutional only), distinct seeds.
SIM_RUNS = [
    (_SCENARIOS[i % 7], _PRESETS[i % 2] if i % 7 == 1 else _PRESETS[(i // 7) % 3], 1000 + i)
    for i in range(28)
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=BACKEND_ROOT / "data" / "lobster" / "2012-06-21")
    parser.add_argument("--sim-runs", type=int, default=len(SIM_RUNS), help="simulator runs to generate (0 = real data only)")
    parser.add_argument("--sim-seconds", type=int, default=3_600)
    parser.add_argument("--sim-share", type=float, default=0.25, help="share of training weight given to simulator rows")
    parser.add_argument("--candidate-output", type=Path, default=BACKEND_ROOT / "models" / "candidates" / "lobster_nasdaq_liquidity_model.pkl")
    parser.add_argument("--report-output", type=Path, default=BACKEND_ROOT / "models" / "candidates" / "lobster_nasdaq_liquidity_report.json")
    return parser.parse_args()


def simulate(run: tuple[str, str, int], seconds: int) -> tuple[np.ndarray, np.ndarray]:
    from backend.src.market.latency_model import LatencyConfig, LatencyMode
    from backend.src.market.oracle import OracleConfig
    from backend.src.market.scenario import get_scenario_config
    from backend.src.market.simulator import MarketSimulator, create_sandbox_agents

    scenario_name, preset, seed = run
    scenario = get_scenario_config(scenario_name)
    sim = MarketSimulator(
        create_sandbox_agents(preset, scenario=scenario, seed=seed),
        duration_seconds=seconds, seed=seed, scenario=scenario,
        oracle_config=OracleConfig(r_bar=100, kappa=0.001, sigma_s=100 * 0.20 / sqrt(252 * 390 * 60) * scenario.oracle_sigma_multiplier),
        latency_config=LatencyConfig(mode=LatencyMode.CUBIC),
    )
    sim.running = True
    observations = []
    while sim.current_time < sim.duration_seconds:
        state = sim.step()
        if state["session_phase"] != "PREOPEN":
            observations.append(observation_from_state(state))
    return build_samples(observations)


def _simulate_job(job: tuple[tuple[str, str, int], int]) -> tuple[np.ndarray, np.ndarray]:
    return simulate(*job)


def fit(parts: list[tuple[np.ndarray, np.ndarray, str]], sim_share: float):
    import lightgbm as lgb

    X = np.vstack([p[0] for p in parts])
    y = np.concatenate([p[1] for p in parts])
    real_n = sum(len(p[1]) for p in parts if p[2] == "real")
    sim_n = sum(len(p[1]) for p in parts if p[2] == "sim")
    sim_weight = (sim_share / (1 - sim_share)) * real_n / sim_n if sim_n and sim_share else 0.0
    weight = np.concatenate([np.full(len(p[1]), 1.0 if p[2] == "real" else sim_weight) for p in parts])
    positives = max(1.0, float(y.sum()))
    params = {**PARAMS, "scale_pos_weight": (len(y) - positives) / positives}
    return lgb.train(params, lgb.Dataset(X, y, weight=weight), num_boost_round=ROUNDS)


def scores(y: np.ndarray, p: np.ndarray) -> dict:
    from sklearn.metrics import average_precision_score, roc_auc_score

    return {
        "roc_auc": round(float(roc_auc_score(y, p)), 4),
        "average_precision": round(float(average_precision_score(y, p)), 4),
        "positive_rate": round(float(y.mean()), 4),
    }


def rule_score(X: np.ndarray) -> np.ndarray:
    """No-learning baseline: distance of spread and depth from their shock thresholds."""
    spread = X[:, FEATURE_NAMES.index("spread_ratio")] / 2.5
    depth = 0.4 / np.maximum(X[:, FEATURE_NAMES.index("depth_ratio")], 1e-3)
    return np.clip(np.maximum(spread, depth), 0, 2) / 2


def main() -> int:
    from sklearn.isotonic import IsotonicRegression

    args = parse_args()
    real: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for orderbook_path in sorted(args.data_dir.glob("*_orderbook_*.csv")):
        message_path = Path(str(orderbook_path).replace("_orderbook_", "_message_"))
        symbol = orderbook_path.name.split("_")[0]
        real[symbol] = build_samples(grid_observations(*load_day(orderbook_path, message_path)))
        print(f"[data] {symbol}: {len(real[symbol][1])} samples, shock rate {real[symbol][1].mean():.3f}", flush=True)
    if not real:
        raise SystemExit(f"No LOBSTER orderbook/message pairs in {args.data_dir}")

    runs = SIM_RUNS[: args.sim_runs]
    with Pool(min(5, max(1, len(runs)))) as pool:
        sims = dict(zip((f"{s}/{p}/{seed}" for s, p, seed in runs), pool.map(_simulate_job, [(r, args.sim_seconds) for r in runs]))) if runs else {}
    for name, (_, y) in sims.items():
        print(f"[data] sim {name}: {len(y)} samples, shock rate {y.mean():.3f}", flush=True)

    def parts(skip_real: str | None = None, skip_sim: str | None = None):
        out = [(X, y, "real") for symbol, (X, y) in real.items() if symbol != skip_real]
        return out + [(X, y, "sim") for name, (X, y) in sims.items() if name != skip_sim]

    held_out_tickers = {}
    for symbol, (X, y) in real.items():
        if y.sum() < MIN_EVAL_POSITIVES:
            continue  # too few shocks to score (deep one-tick books): training data only
        booster = fit(parts(skip_real=symbol), args.sim_share)
        held_out_tickers[symbol] = {"model": scores(y, booster.predict(X)), "rule_baseline": scores(y, rule_score(X))}
        print(f"[eval] held-out {symbol}: {held_out_tickers[symbol]}", flush=True)
    held_out_sims = {}
    for name, (X, y) in sims.items():
        if 0 < y.sum() < len(y):
            booster = fit(parts(skip_sim=name), args.sim_share)
            held_out_sims[name] = {"model": scores(y, booster.predict(X)), "rule_baseline": scores(y, rule_score(X))}
    mean = lambda rows, who, key: round(float(np.mean([r[who][key] for r in rows.values()])), 4) if rows else None

    # Final model: first 80% of every day/run to fit, last 20% to calibrate and pick the threshold.
    train_parts, calib_X, calib_y = [], [], []
    for X, y, kind in parts():
        cut = int(len(y) * 0.8)
        train_parts.append((X[:cut], y[:cut], kind))
        calib_X.append(X[cut + 60:])  # 60 s gap: no label overlaps the training slice
        calib_y.append(y[cut + 60:])
    booster = fit(train_parts, args.sim_share)
    calib_X, calib_y = np.vstack(calib_X), np.concatenate(calib_y)
    raw = booster.predict(calib_X)
    isotonic = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(raw, calib_y)
    calibrated = isotonic.predict(raw)
    threshold = select_probability_threshold(calibrated, calib_y)

    importance = dict(zip(FEATURE_NAMES, booster.feature_importance("gain").round(1).tolist()))
    report = {
        "artifact_type": "lobster_nasdaq_liquidity_shock",
        "venue": "NASDAQ",
        "symbols": sorted(real),
        "source": "LOBSTER sample days (2012-06-21, level 10, order book + messages)",
        "simulator_runs": len(sims),
        "simulator_weight_share": args.sim_share,
        "feature_names": list(FEATURE_NAMES),
        "label_definition": "within the next 60 s: spread >= 2.5x its gated 60 s median, or visible depth <= 40% of it",
        "model": {"library": "lightgbm", "rounds": ROUNDS, **{k: v for k, v in PARAMS.items() if k not in ("verbose", "num_threads")}},
        "held_out_tickers": held_out_tickers,
        "held_out_simulator_runs": held_out_sims,
        "metrics": {
            "held_out_ticker_roc_auc": mean(held_out_tickers, "model", "roc_auc"),
            "held_out_ticker_average_precision": mean(held_out_tickers, "model", "average_precision"),
            "rule_baseline_ticker_roc_auc": mean(held_out_tickers, "rule_baseline", "roc_auc"),
            "rule_baseline_ticker_average_precision": mean(held_out_tickers, "rule_baseline", "average_precision"),
            "held_out_sim_roc_auc": mean(held_out_sims, "model", "roc_auc"),
            "held_out_sim_average_precision": mean(held_out_sims, "model", "average_precision"),
            "calibration_set": scores(calib_y, calibrated),
            "threshold": threshold,
        },
        "feature_importance_gain": importance,
    }
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    knots = np.unique(isotonic.X_thresholds_)
    with args.candidate_output.open("wb") as output:
        pickle.dump({
            **report,
            "model": booster,
            "calibration": {"raw": knots.tolist(), "calibrated": isotonic.predict(knots).tolist()},
        }, output)
    print(json.dumps(report["metrics"], indent=2))
    print(f"[ok] {args.candidate_output}\n[report] {args.report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
