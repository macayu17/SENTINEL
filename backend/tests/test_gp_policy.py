import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.market.gp_policy import (
    GPNode,
    GPPolicyGenome,
    GPTrainingConfig,
    GeneticPolicyModel,
    GeneticProgramTrainer,
)
from backend.src.market.rl_policy import RLPolicyController
from backend.src.agents.rl_agent import RLAgent
from backend.src.market.simulator import MarketSimulator


def test_gp_policy_round_trip(tmp_path):
    genome = GPPolicyGenome(
        action_trees=(
            GPNode(kind="const", value=0.5),
            GPNode(kind="feature", value=4),
            GPNode(
                kind="add",
                children=(GPNode(kind="feature", value=7), GPNode(kind="const", value=-0.25)),
            ),
        )
    )
    model = GeneticPolicyModel(genome)
    path = tmp_path / "gp_policy.json"
    model.save(path, metadata={"name": "test"})

    loaded_model = GeneticPolicyModel.load(path)
    action, _ = loaded_model.predict(np.zeros(13, dtype=np.float32))

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["policy_type"] == "gp"
    assert action.shape == (3,)
    assert np.isfinite(action).all()


def test_gp_policy_controller_can_queue_loaded_model(tmp_path):
    genome = GPPolicyGenome(
        action_trees=(
            GPNode(kind="const", value=0.0),
            GPNode(kind="const", value=0.0),
            GPNode(kind="const", value=0.0),
        )
    )
    path = tmp_path / "gp_policy.json"
    GeneticPolicyModel(genome).save(path)

    rl_agent = RLAgent("RL_MM", initial_capital=100000.0)
    simulator = MarketSimulator(agents=[rl_agent], initial_price=100.0, duration_seconds=10)
    simulator.reset(seed=21)

    controller = RLPolicyController(
        model_path=str(path),
        rl_agent_id="RL_MM",
        policy_kind="gp",
    )
    action = controller.prepare_step(simulator)
    simulator.step()

    assert action == (0.0, 0.0, 0.0)
    assert len(rl_agent.active_orders) == 2


def test_genetic_program_trainer_smoke():
    trainer = GeneticProgramTrainer(
        GPTrainingConfig(
            population_size=4,
            generations=1,
            elite_size=1,
            evaluation_episodes=1,
            episode_duration=20,
            seed=7,
        )
    )

    best, history = trainer.train()

    assert best.fitness is not None
    assert np.isfinite(best.fitness)
    assert len(history) == 1
