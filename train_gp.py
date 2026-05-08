"""Train a genetic-programming market-making policy for SENTINEL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.market.gp_policy import GPTrainingConfig, GeneticPolicyModel, GeneticProgramTrainer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a GP market-making policy")
    parser.add_argument("--population-size", type=int, default=24)
    parser.add_argument("--generations", type=int, default=8)
    parser.add_argument("--elite-size", type=int, default=3)
    parser.add_argument("--evaluation-episodes", type=int, default=2)
    parser.add_argument("--episode-duration", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--save-path", type=str, default="backend/models/gp_market_maker.json")
    return parser.parse_args()


def main(args: argparse.Namespace) -> None:
    config = GPTrainingConfig(
        population_size=args.population_size,
        generations=args.generations,
        elite_size=args.elite_size,
        evaluation_episodes=args.evaluation_episodes,
        episode_duration=args.episode_duration,
        seed=args.seed,
    )
    trainer = GeneticProgramTrainer(config)
    best_genome, history = trainer.train()

    save_path = Path(args.save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    model = GeneticPolicyModel(best_genome)
    model.save(
        save_path,
        metadata={
            "population_size": args.population_size,
            "generations": args.generations,
            "evaluation_episodes": args.evaluation_episodes,
            "episode_duration": args.episode_duration,
            "seed": args.seed,
            "history": history,
        },
    )

    summary = {
        "save_path": str(save_path),
        "best_fitness": best_genome.fitness,
        "metrics": best_genome.metrics,
        "history": history,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main(parse_args())
