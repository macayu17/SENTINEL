#!/usr/bin/env python3
"""Debug script to check what actions the trained model is predicting."""

import sys
from pathlib import Path

import numpy as np
from stable_baselines3 import PPO

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.prediction.intraday_rl.environment import IntradayEnvConfig, IntradayTradingEnv
from src.prediction.intraday_rl.features import (
    build_intraday_features,
    load_ohlcv_csv,
    split_sessions,
)

def main():
    csv_path = "../data/historical_1m.csv"
    model_path = "./models/rl_training/my_model_ppo"
    
    print(f"📂 Loading model from {model_path}")
    model = PPO.load(model_path)
    print(f"✅ Model loaded")
    
    print(f"\n📊 Loading data from {csv_path}")
    raw = load_ohlcv_csv(csv_path)
    featured = build_intraday_features(raw)
    sessions = split_sessions(featured)
    print(f"✅ Loaded {len(sessions)} sessions")
    
    # Test on first 3 sessions
    env_config = IntradayEnvConfig()
    env = IntradayTradingEnv(sessions=sessions, config=env_config)
    
    action_counts = {"HOLD": 0, "BUY": 0, "SELL": 0}
    trade_count = 0
    
    for session_idx in range(min(3, len(sessions))):
        print(f"\n{'='*70}")
        print(f"Session {session_idx}")
        print(f"{'='*70}")
        
        obs, info = env.reset(options={"session_index": session_idx})
        done = False
        step = 0
        session_trades = 0
        
        while not done and step < 100:  # Limit to first 100 steps
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, done, _, step_info = env.step(int(action))
            
            action_label = step_info["action"]
            action_counts[action_label] += 1
            
            if step_info.get("trade_event") and step_info["trade_event"].get("status") == "filled":
                session_trades += 1
                trade_event = step_info["trade_event"]
                print(f"  Step {step:3d}: {action_label:6s} @ {trade_event['price']:8.2f} - {trade_event['side']:4s} {trade_event.get('reason', '')}")
            elif step % 10 == 0:  # Print every 10 steps
                print(f"  Step {step:3d}: {action_label:6s} | Position: {step_info['position']} | Equity: {step_info['equity']:12,.0f}")
            
            step += 1
        
        trade_count += session_trades
        print(f"✅ Session {session_idx} complete: {session_trades} trades")
    
    print(f"\n{'='*70}")
    print(f"Summary across 3 sessions:")
    print(f"  HOLD:  {action_counts['HOLD']} steps")
    print(f"  BUY:   {action_counts['BUY']} steps")
    print(f"  SELL:  {action_counts['SELL']} steps")
    print(f"  Total trades: {trade_count}")
    print(f"{'='*70}")

if __name__ == "__main__":
    main()
