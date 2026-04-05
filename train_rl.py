"""Main RL training script for the Sentinel Market Maker."""

import os
import sys
import gymnasium as gym
import numpy as np

# Append backend to path so we can import modules
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend', 'src'))

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, EvalCallback, CallbackList
from stable_baselines3.common.env_util import DummyVecEnv
from stable_baselines3.common.monitor import Monitor

from backend.src.market.simulator import MarketSimulator
from backend.src.market.rl_env import MarketMakerEnv
from backend.src.agents.noise import NoiseAgent
from backend.src.agents.hft_agent import HFTAgent
from backend.src.agents.retail import RetailAgent
from backend.src.agents.informed import InformedAgent
from backend.src.agents.liquidity_trader import LiquidityTraderAgent
from backend.src.agents.rl_agent import RLAgent
from backend.src.agents.institutional import InstitutionalAgent

class MetricsLoggerCallback(BaseCallback):
    """
    Custom callback for logging structured market-making metrics
    to TensorBoard over the course of training.
    """
    def __init__(self, verbose=0):
        super().__init__(verbose)
        self.pnls = []
        self.inventories = []
        self.drawdowns = []
        self.rewards = []
        self.fill_rates = []

    def _on_step(self) -> bool:
        # Extract info dict returned sequentially by our environment
        infos = self.locals.get("infos", [])
        for info in infos:
            if info:
                self.pnls.append(info.get("pnl", 0))
                self.inventories.append(abs(info.get("inventory", 0)))
                self.drawdowns.append(info.get("drawdown", 0))
                self.fill_rates.append(info.get("fill_rate", 0))
                
        rewards = self.locals.get("rewards")
        if rewards is not None:
            self.rewards.append(float(rewards[0]))
            
            # Check for end of episode
            if self.locals.get("dones", [False])[0]:
                final_pnl = self.pnls[-1] if self.pnls else 0.0
                mean_inv = np.mean(self.inventories) if self.inventories else 0.0
                max_dd = np.max(self.drawdowns) if self.drawdowns else 0.0
                cum_reward = float(np.sum(self.rewards)) if self.rewards else 0.0
                avg_fill_rate = float(np.mean(self.fill_rates)) if self.fill_rates else 0.0
                
                self.logger.record("market_maker/final_pnl", final_pnl)
                self.logger.record("market_maker/mean_abs_inventory", mean_inv)
                self.logger.record("market_maker/max_drawdown", max_dd)
                self.logger.record("market_maker/cumulative_reward", cum_reward)
                self.logger.record("market_maker/avg_fill_rate", avg_fill_rate)
                
                self.pnls.clear()
                self.inventories.clear()
                self.drawdowns.clear()
                self.rewards.clear()
                self.fill_rates.clear()
        return True

def create_env():
    # 1. Initialize heterogeneous market population + InstitutionalAgent
    agents = [
        RLAgent("RL_MM", initial_capital=100000.0),
        HFTAgent("HFT_1", position_limit=600),
        InformedAgent("INF_1", signal_probability=0.02, signal_accuracy=0.62),
        LiquidityTraderAgent("LIQ_1", start_probability=0.03),
        RetailAgent("RET_1"),
        NoiseAgent("Noise_1", order_rate=0.35),
        NoiseAgent("Noise_2", order_rate=0.45),
        InstitutionalAgent("INST_1", target_quantity=20_000, execution_window=1000)
    ]
    
    # 2. Build the Simulator logic
    sim = MarketSimulator(agents=agents, initial_price=100.0, duration_seconds=1000)
    
    # 3. Create the Gym Environment matching wrapper
    env = MarketMakerEnv(simulator=sim, rl_agent_id="RL_MM")
    # Wrap in Monitor to ensure base tracking works with EvalCallback
    env = Monitor(env)
    return env

def train():
    print("Setting up the Reinforcement Learning Market-Maker Environment...")
    
    # Create main training environment
    train_env = DummyVecEnv([create_env])
    
    # Create separate evaluation environment
    eval_env = DummyVecEnv([create_env])

    print("Initializing PPO Agent...")
    model = PPO(
        "MlpPolicy", 
        train_env, 
        verbose=1, 
        learning_rate=3e-4, 
        n_steps=1000, 
        batch_size=64, 
        tensorboard_log="./tensorboard_logs/"
    )
    
    # Custom logger for deep specific market metrics
    metrics_callback = MetricsLoggerCallback()
    
    # Evaluation callback for episodic testing
    os.makedirs("./models/eval", exist_ok=True)
    eval_callback = EvalCallback(
        eval_env, 
        best_model_save_path='./models/best_model/',
        log_path='./models/eval/', 
        eval_freq=2000,          # Evaluate every 2000 steps
        deterministic=True, 
        render=False
    )
    
    # Combine callbacks
    callbacks = CallbackList([metrics_callback, eval_callback])
    
    TOTAL_TIMESTEPS = 10_000
    
    print(f"Starting Training for {TOTAL_TIMESTEPS} timesteps with episodic evaluations...")
    model.learn(total_timesteps=TOTAL_TIMESTEPS, callback=callbacks)
    
    print("Training Complete. Saving final model...")
    os.makedirs("./models", exist_ok=True)
    model.save("./models/ppo_market_maker_final")
    
    print("Models saved successfully!")
    
if __name__ == "__main__":
    train()
