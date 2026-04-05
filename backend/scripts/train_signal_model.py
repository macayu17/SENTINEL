#!/usr/bin/env python3
"""
Train a signal model from simulation data.

Usage:
    python backend/scripts/train_signal_model.py [--output-path path/to/model.pkl]
"""

import sys
import argparse
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.market.simulator import MarketSimulator
from src.agents.market_maker import MarketMakerAgent
from src.agents.hft_agent import HFTAgent
from src.agents.institutional import InstitutionalAgent
from src.agents.retail import RetailAgent
from src.agents.informed import InformedAgent
from src.agents.noise import NoiseAgent
from src.prediction.training_data import generate_training_data_from_simulation, TrainingDataCollector
from src.prediction.signal_model import SignalModel
from src.utils.logger import get_logger

logger = get_logger("train_signal_model")


def run_training_simulation(duration_seconds: int = 23_400) -> MarketSimulator:
    """Run a simulation to generate training data."""
    logger.info(f"Starting training simulation for {duration_seconds} seconds...")
    
    agents = [
        MarketMakerAgent(name="MM1", latency_seconds=0.01),
        MarketMakerAgent(name="MM2", latency_seconds=0.012),
        HFTAgent(name="HFT1", latency_seconds=0.005),
        InstitutionalAgent(name="Inst1", latency_seconds=0.1),
        InstitutionalAgent(name="Inst2", latency_seconds=0.12),
        RetailAgent(name="Retail1", latency_seconds=0.5),
        RetailAgent(name="Retail2", latency_seconds=0.6),
        InformedAgent(name="Informed1", latency_seconds=0.2),
        NoiseAgent(name="Noise1", latency_seconds=1.0),
        NoiseAgent(name="Noise2", latency_seconds=1.2),
    ]
    
    simulator = MarketSimulator(
        agents=agents,
        initial_price=100.0,
        duration_seconds=duration_seconds,
        mode="SANDBOX",
    )
    
    logger.info(f"Running simulator with {len(agents)} agents...")
    simulator.run()
    logger.info(f"Simulation complete. Generated {simulator.step_count} steps.")
    logger.info(f"State history length: {len(simulator._state_history)}")
    
    return simulator


def train_signal_model(output_path: Path) -> None:
    """Main training pipeline."""
    # Step 1: Generate training data
    logger.info("=" * 60)
    logger.info("PHASE 1: Generating training data")
    logger.info("=" * 60)
    
    simulator = run_training_simulation(duration_seconds=23_400)
    
    # Step 2: Collect and prepare data
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 2: Collecting training data from simulator")
    logger.info("=" * 60)
    
    collector = TrainingDataCollector(price_movement_threshold=0.001)
    training_data = generate_training_data_from_simulation(
        simulator,
        collector,
        sample_interval=5,
    )
    
    logger.info(f"Collected {len(training_data)} training data points")
    
    # Convert to DataFrame
    df = collector.create_training_dataframe()
    logger.info(f"DataFrame shape: {df.shape}")
    logger.info(f"Label distribution:\n{df['label'].value_counts()}")
    
    # Step 3: Train model
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 3: Training signal model")
    logger.info("=" * 60)
    
    model = SignalModel()
    X = df[SignalModel.FEATURES]
    y = df["label"]
    
    metrics = model.train(X, y, test_size=0.2, random_state=42)
    
    logger.info(f"Train Accuracy: {metrics['train_accuracy']:.4f}")
    logger.info(f"Test Accuracy: {metrics['test_accuracy']:.4f}")
    logger.info(f"Training samples: {metrics['n_training_samples']}")
    logger.info(f"Test samples: {metrics['n_test_samples']}")
    
    # Print detailed classification report
    logger.info("\nClassification Report:")
    for label, stats in metrics['classification_report'].items():
        if label not in ['accuracy', 'macro avg', 'weighted avg']:
            logger.info(
                f"  {label}: "
                f"precision={stats.get('precision', 0):.3f} "
                f"recall={stats.get('recall', 0):.3f} "
                f"f1={stats.get('f1-score', 0):.3f}"
            )
    
    # Step 4: Save model
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 4: Saving trained model")
    logger.info("=" * 60)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(output_path)
    logger.info(f"✓ Model saved to: {output_path}")
    
    # Verify model loads
    loaded_model = SignalModel.load(output_path)
    logger.info(f"✓ Model loaded and verified")
    
    # Test inference on sample
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 5: Testing inference")
    logger.info("=" * 60)
    
    sample = df.iloc[0]
    features = {col: float(sample[col]) for col in SignalModel.FEATURES}
    
    predicted_action = loaded_model.predict(features)
    predicted_probs = loaded_model.predict_proba(features)
    
    logger.info(f"Sample input: {features}")
    logger.info(f"Predicted action: {predicted_action}")
    logger.info(f"Probabilities: BUY={predicted_probs['BUY']:.3f}, SELL={predicted_probs['SELL']:.3f}, HOLD={predicted_probs['HOLD']:.3f}")
    
    logger.info("\n" + "=" * 60)
    logger.info("TRAINING COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train signal model from simulation data")
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path(__file__).parent.parent / "models" / "signal_model.pkl",
        help="Output path for trained model",
    )
    
    args = parser.parse_args()
    
    try:
        train_signal_model(args.output_path)
        logger.info("\n✓ Training pipeline completed successfully")
    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        sys.exit(1)
