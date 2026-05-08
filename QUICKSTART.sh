#!/bin/bash
# Quick-start guide for trained model + real market integration

set -e  # Exit on error

SENTINEL_ROOT="/Users/anindhithsankanna/CS Projects/Sentinel"
BACKEND_DIR="$SENTINEL_ROOT/backend"
MODELS_DIR="$BACKEND_DIR/models"

echo "=========================================="
echo "SENTINEL Signal Model Quick Start"
echo "=========================================="
echo ""

# Ensure models directory exists
mkdir -p "$MODELS_DIR"

# Step 1: Run integration tests
echo "Step 1: Running integration tests..."
echo "------------------------------------"
cd "$BACKEND_DIR"
python scripts/test_integration.py || {
    echo "❌ Integration tests failed"
    exit 1
}

echo ""
echo "✓ Integration tests passed"
echo ""

# Step 2: Train signal model
echo "Step 2: Training signal model..."
echo "--------------------------------"
echo "This will:"
echo "  - Run simulator with 10 agents for ~6.5 hours of market time"
echo "  - Generate ~4,600 training data points"
echo "  - Train logistic regression model"
echo "  - Save to $MODELS_DIR/signal_model.pkl"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    python scripts/train_signal_model.py --output-path "$MODELS_DIR/signal_model.pkl" || {
        echo "❌ Training failed"
        exit 1
    }
    echo ""
    echo "✓ Model trained and saved"
else
    echo "Skipped model training. Using rule-based fallback."
fi

echo ""
echo "=========================================="
echo "Next Steps"
echo "=========================================="
echo ""
echo "1. Start backend with trained model (SIMULATION):"
echo "   cd $BACKEND_DIR"
echo "   SIMULATION_MODE=SIMULATION python -m uvicorn src.api.main:app --reload"
echo ""
echo "2. Or start with real market data (LIVE_SHADOW):"
echo "   cd $BACKEND_DIR"
echo "   SIMULATION_MODE=LIVE_SHADOW python -m uvicorn src.api.main:app --reload"
echo ""
echo "3. In another terminal, start frontend:"
echo "   cd $SENTINEL_ROOT/frontend"
echo "   npm run dev"
echo ""
echo "4. Open browser:"
echo "   http://localhost:3000"
echo ""
echo "=========================================="
echo "Model Status"
echo "=========================================="
if [ -f "$MODELS_DIR/signal_model.pkl" ]; then
    ls -lh "$MODELS_DIR/signal_model.pkl"
    echo "✓ Model file exists"
else
    echo "⚠ No trained model found (using rule-based fallback)"
fi
