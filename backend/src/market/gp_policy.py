"""Genetic-programming policy search for the market-making agent."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import random
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

from .training_setup import create_market_maker_env


UNARY_OPS = ("neg", "abs", "tanh")
BINARY_OPS = ("add", "sub", "mul", "div")


def _safe_float(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(-8.0, min(8.0, value))


@dataclass
class GPNode:
    kind: str
    value: Any = None
    children: tuple["GPNode", ...] = ()

    def evaluate(self, features: np.ndarray) -> float:
        if self.kind == "const":
            return _safe_float(float(self.value))
        if self.kind == "feature":
            index = int(self.value)
            if index < 0 or index >= len(features):
                return 0.0
            return _safe_float(float(features[index]))

        if not self.children:
            return 0.0

        child_values = [child.evaluate(features) for child in self.children]
        op = self.kind

        if op == "neg":
            result = -child_values[0]
        elif op == "abs":
            result = abs(child_values[0])
        elif op == "tanh":
            result = math.tanh(child_values[0])
        elif op == "add":
            result = child_values[0] + child_values[1]
        elif op == "sub":
            result = child_values[0] - child_values[1]
        elif op == "mul":
            result = child_values[0] * child_values[1]
        elif op == "div":
            denom = child_values[1]
            result = child_values[0] / denom if abs(denom) > 1e-6 else child_values[0]
        else:
            result = 0.0

        return _safe_float(result)

    def clone(self) -> "GPNode":
        return GPNode(
            kind=self.kind,
            value=self.value,
            children=tuple(child.clone() for child in self.children),
        )

    def depth(self) -> int:
        if not self.children:
            return 1
        return 1 + max(child.depth() for child in self.children)

    def collect_paths(self, prefix: tuple[int, ...] = ()) -> list[tuple[int, ...]]:
        paths = [prefix]
        for index, child in enumerate(self.children):
            paths.extend(child.collect_paths(prefix + (index,)))
        return paths

    def get_subtree(self, path: tuple[int, ...]) -> "GPNode":
        node = self
        for index in path:
            node = node.children[index]
        return node

    def replace_subtree(self, path: tuple[int, ...], replacement: "GPNode") -> "GPNode":
        if not path:
            return replacement.clone()

        index = path[0]
        updated_children = list(self.children)
        updated_children[index] = updated_children[index].replace_subtree(path[1:], replacement)
        return GPNode(kind=self.kind, value=self.value, children=tuple(updated_children))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "children": [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GPNode":
        return cls(
            kind=str(payload["kind"]),
            value=payload.get("value"),
            children=tuple(cls.from_dict(child) for child in payload.get("children", [])),
        )


def random_terminal(rng: random.Random, feature_dim: int) -> GPNode:
    if rng.random() < 0.55:
        return GPNode(kind="feature", value=rng.randrange(feature_dim))
    return GPNode(kind="const", value=round(rng.uniform(-2.0, 2.0), 4))


def random_tree(rng: random.Random, feature_dim: int, max_depth: int) -> GPNode:
    if max_depth <= 1 or rng.random() < 0.35:
        return random_terminal(rng, feature_dim)

    op = rng.choice(UNARY_OPS + BINARY_OPS)
    if op in UNARY_OPS:
        return GPNode(kind=op, children=(random_tree(rng, feature_dim, max_depth - 1),))

    return GPNode(
        kind=op,
        children=(
            random_tree(rng, feature_dim, max_depth - 1),
            random_tree(rng, feature_dim, max_depth - 1),
        ),
    )


@dataclass
class GPPolicyGenome:
    action_trees: tuple[GPNode, GPNode, GPNode]
    fitness: Optional[float] = None
    metrics: dict[str, float] = field(default_factory=dict)

    def clone(self) -> "GPPolicyGenome":
        return GPPolicyGenome(
            action_trees=tuple(tree.clone() for tree in self.action_trees),
            fitness=self.fitness,
            metrics=dict(self.metrics),
        )

    def predict(self, observation: np.ndarray, deterministic: bool = True) -> tuple[np.ndarray, None]:
        features = np.asarray(observation, dtype=np.float32)
        raw_actions = np.array(
            [tree.evaluate(features) for tree in self.action_trees],
            dtype=np.float32,
        )
        action = np.tanh(np.nan_to_num(raw_actions, nan=0.0, posinf=0.0, neginf=0.0))
        return action.astype(np.float32), None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fitness": self.fitness,
            "metrics": self.metrics,
            "action_trees": [tree.to_dict() for tree in self.action_trees],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GPPolicyGenome":
        trees = tuple(GPNode.from_dict(tree) for tree in payload["action_trees"])
        if len(trees) != 3:
            raise ValueError("GP policy must contain exactly 3 action trees")
        return cls(
            action_trees=trees,
            fitness=payload.get("fitness"),
            metrics={k: float(v) for k, v in payload.get("metrics", {}).items()},
        )


class GeneticPolicyModel:
    """Prediction wrapper that matches the PPO `.predict()` interface."""

    def __init__(self, genome: GPPolicyGenome) -> None:
        self.genome = genome

    def predict(self, observation: np.ndarray, deterministic: bool = True) -> tuple[np.ndarray, None]:
        return self.genome.predict(observation, deterministic=deterministic)

    def save(self, path: str | Path, metadata: Optional[dict[str, Any]] = None) -> None:
        payload = {
            "policy_type": "gp",
            "metadata": metadata or {},
            "genome": self.genome.to_dict(),
        }
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "GeneticPolicyModel":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(GPPolicyGenome.from_dict(payload["genome"]))


@dataclass
class GPTrainingConfig:
    population_size: int = 24
    generations: int = 8
    elite_size: int = 3
    tournament_size: int = 3
    mutation_rate: float = 0.30
    crossover_rate: float = 0.75
    max_tree_depth: int = 4
    evaluation_episodes: int = 2
    episode_duration: int = 300
    initial_price: float = 100.0
    feature_dim: int = 13
    seed: int = 42


class GeneticProgramTrainer:
    def __init__(self, config: GPTrainingConfig) -> None:
        self.config = config
        self.rng = random.Random(config.seed)

    def random_genome(self) -> GPPolicyGenome:
        return GPPolicyGenome(
            action_trees=tuple(
                random_tree(self.rng, self.config.feature_dim, self.config.max_tree_depth)
                for _ in range(3)
            )
        )

    def _mutate_tree(self, tree: GPNode) -> GPNode:
        paths = tree.collect_paths()
        target_path = self.rng.choice(paths)
        subtree = tree.get_subtree(target_path)

        if subtree.kind == "const" and self.rng.random() < 0.5:
            mutated_value = round(float(subtree.value) + self.rng.uniform(-0.75, 0.75), 4)
            replacement = GPNode(kind="const", value=mutated_value)
        else:
            remaining_depth = max(1, self.config.max_tree_depth - len(target_path))
            replacement = random_tree(self.rng, self.config.feature_dim, remaining_depth)

        candidate = tree.replace_subtree(target_path, replacement)
        return candidate if candidate.depth() <= self.config.max_tree_depth + 1 else tree.clone()

    def mutate(self, genome: GPPolicyGenome) -> GPPolicyGenome:
        trees = [tree.clone() for tree in genome.action_trees]
        tree_index = self.rng.randrange(len(trees))
        trees[tree_index] = self._mutate_tree(trees[tree_index])
        return GPPolicyGenome(action_trees=tuple(trees))

    def crossover(self, left: GPPolicyGenome, right: GPPolicyGenome) -> GPPolicyGenome:
        trees = [tree.clone() for tree in left.action_trees]
        tree_index = self.rng.randrange(len(trees))
        left_paths = trees[tree_index].collect_paths()
        right_paths = right.action_trees[tree_index].collect_paths()
        left_path = self.rng.choice(left_paths)
        right_subtree = right.action_trees[tree_index].get_subtree(self.rng.choice(right_paths))
        candidate = trees[tree_index].replace_subtree(left_path, right_subtree)
        trees[tree_index] = candidate if candidate.depth() <= self.config.max_tree_depth + 1 else trees[tree_index]
        return GPPolicyGenome(action_trees=tuple(trees))

    def tournament_select(self, population: list[GPPolicyGenome]) -> GPPolicyGenome:
        contenders = self.rng.sample(population, k=min(self.config.tournament_size, len(population)))
        best = max(contenders, key=lambda genome: genome.fitness if genome.fitness is not None else -float("inf"))
        return best.clone()

    def evaluate_genome(self, genome: GPPolicyGenome) -> float:
        rewards: list[float] = []
        pnls: list[float] = []
        drawdowns: list[float] = []
        inventories: list[float] = []
        fill_rates: list[float] = []

        for episode_index in range(self.config.evaluation_episodes):
            env = create_market_maker_env(
                initial_price=self.config.initial_price,
                duration_seconds=self.config.episode_duration,
            )
            observation, _ = env.reset(seed=self.config.seed + (episode_index * 97))

            terminated = False
            truncated = False
            total_reward = 0.0
            last_info: dict[str, Any] = {}

            while not (terminated or truncated):
                action, _ = genome.predict(observation)
                observation, reward, terminated, truncated, last_info = env.step(action)
                total_reward += float(reward)

            rewards.append(total_reward)
            pnls.append(float(last_info.get("pnl", 0.0)))
            drawdowns.append(float(last_info.get("drawdown", 0.0)))
            inventories.append(abs(float(last_info.get("inventory", 0.0))) / 5000.0)
            fill_rates.append(float(last_info.get("fill_rate", 0.0)))

        avg_reward = float(np.mean(rewards)) if rewards else 0.0
        avg_pnl = float(np.mean(pnls)) / 50.0 if pnls else 0.0
        avg_drawdown = float(np.mean(drawdowns)) / 75.0 if drawdowns else 0.0
        avg_inventory = float(np.mean(inventories)) if inventories else 0.0
        avg_fill = float(np.mean(fill_rates)) if fill_rates else 0.0

        fitness = avg_reward + avg_pnl + (0.05 * avg_fill) - (0.8 * avg_inventory) - (0.4 * avg_drawdown)
        genome.fitness = float(fitness)
        genome.metrics = {
            "avg_reward": avg_reward,
            "avg_pnl": float(np.mean(pnls)) if pnls else 0.0,
            "avg_drawdown": float(np.mean(drawdowns)) if drawdowns else 0.0,
            "avg_inventory_ratio": avg_inventory,
            "avg_fill_rate": avg_fill,
        }
        return genome.fitness

    def _ensure_scored(self, population: Iterable[GPPolicyGenome]) -> None:
        for genome in population:
            if genome.fitness is None:
                self.evaluate_genome(genome)

    def train(self) -> tuple[GPPolicyGenome, list[dict[str, float]]]:
        if self.config.elite_size >= self.config.population_size:
            raise ValueError("elite_size must be smaller than population_size")

        population = [self.random_genome() for _ in range(self.config.population_size)]
        history: list[dict[str, float]] = []

        for generation in range(self.config.generations):
            self._ensure_scored(population)
            population.sort(key=lambda genome: genome.fitness if genome.fitness is not None else -float("inf"), reverse=True)

            best = population[0]
            avg_fitness = float(
                np.mean([genome.fitness for genome in population if genome.fitness is not None])
            )
            history.append(
                {
                    "generation": float(generation),
                    "best_fitness": float(best.fitness or 0.0),
                    "avg_fitness": avg_fitness,
                    "best_avg_reward": best.metrics.get("avg_reward", 0.0),
                    "best_avg_pnl": best.metrics.get("avg_pnl", 0.0),
                }
            )

            next_population = [genome.clone() for genome in population[: self.config.elite_size]]

            while len(next_population) < self.config.population_size:
                parent_a = self.tournament_select(population)
                child = parent_a

                if self.rng.random() < self.config.crossover_rate:
                    parent_b = self.tournament_select(population)
                    child = self.crossover(parent_a, parent_b)

                if self.rng.random() < self.config.mutation_rate:
                    child = self.mutate(child)

                next_population.append(child)

            population = next_population

        self._ensure_scored(population)
        population.sort(key=lambda genome: genome.fitness if genome.fitness is not None else -float("inf"), reverse=True)
        return population[0], history
