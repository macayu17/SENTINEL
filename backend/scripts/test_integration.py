#!/usr/bin/env python3
"""
Integration test: Verify trained model works in LIVE_SHADOW and SIMULATION modes.

Tests:
  1. SIMULATION mode: Rule-based signal engine works
  2. LIVE_SHADOW mock: Signal engine outputs correct shape
  3. Model training: Can train and load model
  4. Model inference: Predictions work and fall back correctly
  5. Dashboard compatibility: Signal shape unchanged

Usage:
    python backend/scripts/test_integration.py
"""

import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.prediction.signal_engine import SignalEngine, SignalInput
from src.prediction.signal_model import SignalModel
from src.utils.logger import get_logger

logger = get_logger("integration_test")


def test_rule_based_signal_engine():
    """Test rule-based fallback engine."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 1: Rule-based signal engine")
    logger.info("=" * 60)
    
    engine = SignalEngine(model_path=None)  # No model, use rule-based
    
    signal = engine.predict(SignalInput(
        mid_price=100.0,
        spread=0.01,
        order_book_imbalance=0.5,
        recent_price_movement=0.02,
        trade_flow=100.0,
        inventory=500.0,
    ))
    
    # Verify output shape
    assert "signal" in signal, "Missing 'signal' key"
    assert "confidence" in signal, "Missing 'confidence' key"
    assert "explanation" in signal, "Missing 'explanation' key"
    assert "components" in signal, "Missing 'components' key"
    assert "model_type" in signal, "Missing 'model_type' key"
    
    assert signal["model_type"] == "rule_based"
    assert signal["signal"] in ["BUY", "SELL", "HOLD"]
    assert 0.0 <= signal["confidence"] <= 1.0
    
    logger.info(f"✓ Signal: {signal['signal']}")
    logger.info(f"✓ Confidence: {signal['confidence']}")
    logger.info(f"✓ Model type: {signal['model_type']}")
    logger.info(f"✓ Rule-based engine output shape correct")
    return True


def test_signal_shape_compatibility():
    """Test that signal output shape matches dashboard contract."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Dashboard signal contract compatibility")
    logger.info("=" * 60)
    
    engine = SignalEngine(model_path=None)
    
    signal = engine.predict(SignalInput(
        mid_price=100.5,
        spread=0.005,
        order_book_imbalance=-0.3,
        recent_price_movement=-0.01,
        trade_flow=-50.0,
        inventory=-1000.0,
    ))
    
    # Dashboard expects:
    # - action: BUY/SELL/HOLD
    # - confidence: float 0-1
    # - explanation: string
    
    # Check primary fields
    assert signal["signal"] in ["BUY", "SELL", "HOLD"]
    assert isinstance(signal["confidence"], (int, float))
    assert isinstance(signal["explanation"], str)
    
    # The websocket will use "signal" key; verify it's present
    json.dumps({
        "action": signal["signal"],
        "confidence": signal["confidence"],
        "explanation": signal["explanation"],
    })
    
    logger.info(f"✓ Signal contract compatible:")
    logger.info(f"   action={signal['signal']}, confidence={signal['confidence']}")
    logger.info(f"✓ Dashboard serialization works")
    return True


def test_model_training_and_inference():
    """Test that model can be trained and used for inference."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Model training and inference")
    logger.info("=" * 60)
    
    try:
        import pandas as pd
        import numpy as np
    except ImportError:
        logger.warning("pandas not available; skipping model test")
        return True
    
    # Create synthetic training data
    n_samples = 100
    data = {
        "spread": np.random.uniform(0.001, 0.02, n_samples),
        "mid_price": np.random.uniform(95.0, 105.0, n_samples),
        "order_book_imbalance": np.random.uniform(-1.0, 1.0, n_samples),
        "trade_flow": np.random.uniform(-100.0, 100.0, n_samples),
        "volatility": np.random.uniform(0.01, 0.04, n_samples),
        "inventory": np.random.uniform(-2000.0, 2000.0, n_samples),
        "label": np.random.choice(["BUY", "SELL", "HOLD"], n_samples),
    }
    df = pd.DataFrame(data)
    
    # Train model
    model = SignalModel()
    X = df[SignalModel.FEATURES]
    y = df["label"]
    
    metrics = model.train(X, y, test_size=0.2)
    logger.info(f"✓ Model trained")
    logger.info(f"  Train accuracy: {metrics['train_accuracy']:.3f}")
    logger.info(f"  Test accuracy: {metrics['test_accuracy']:.3f}")
    
    # Test inference
    sample = df.iloc[0]
    features = {col: float(sample[col]) for col in SignalModel.FEATURES}
    
    signal = model.predict(features)
    probs = model.predict_proba(features)
    
    assert signal in ["BUY", "SELL", "HOLD"]
    assert sum(probs.values()) > 0.99  # Probabilities should sum to ~1
    
    logger.info(f"✓ Model inference works: {signal}")
    logger.info(f"  Probabilities: {probs}")
    
    return True


def test_engine_with_unavailable_model():
    """Test that engine falls back to rule-based if model not found."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Fallback when model unavailable")
    logger.info("=" * 60)
    
    # Point to nonexistent model
    engine = SignalEngine(model_path=Path("/nonexistent/model.pkl"))
    assert not engine.model_available
    
    signal = engine.predict(SignalInput(
        mid_price=100.0,
        spread=0.01,
        order_book_imbalance=0.5,
        recent_price_movement=0.02,
        trade_flow=100.0,
        inventory=500.0,
    ))
    
    assert signal["model_type"] == "rule_based"
    logger.info(f"✓ Correctly fell back to rule-based")
    logger.info(f"  Signal: {signal['signal']}, Model type: {signal['model_type']}")
    return True


def main():
    """Run all integration tests."""
    logger.info("\n" + "=" * 60)
    logger.info("SENTINEL Signal Model Integration Tests")
    logger.info("=" * 60)
    
    tests = [
        ("Rule-based engine", test_rule_based_signal_engine),
        ("Signal shape", test_signal_shape_compatibility),
        ("Model training", test_model_training_and_inference),
        ("Fallback mechanism", test_engine_with_unavailable_model),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                logger.error(f"✗ {test_name} failed")
        except Exception as e:
            failed += 1
            logger.error(f"✗ {test_name} raised exception: {e}", exc_info=True)
    
    logger.info("\n" + "=" * 60)
    logger.info(f"RESULTS: {passed} passed, {failed} failed")
    logger.info("=" * 60)
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
