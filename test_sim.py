import sys
import os
import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), 'backend', 'src'))
from backend.src.market.simulator import MarketSimulator
from backend.src.agents.noise import NoiseAgent
from backend.src.agents.hft_agent import HFTAgent
from backend.src.agents.retail import RetailAgent
from backend.src.agents.informed import InformedAgent
from backend.src.agents.liquidity_trader import LiquidityTraderAgent
from backend.src.agents.rl_agent import RLAgent
from backend.src.agents.institutional import InstitutionalAgent

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

sim = MarketSimulator(agents=agents, initial_price=100.0, duration_seconds=1000)
sim.reset()
spreads = []
for i in range(1000):
    sim.step()
    state = sim.get_market_state()
    spreads.append(state['spread'])
    
print(f"Mean spread: {np.mean(spreads)}")
print(f"Max spread: {np.max(spreads)}")
print(f"Final price: {state['mid_price']}")
