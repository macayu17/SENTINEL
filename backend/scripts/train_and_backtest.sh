#!/bin/bash

# Simple script: Train RL model and backtest automatically
# Usage: ./train_and_backtest.sh my_model 250000

MODEL_NAME="${1:-experiment_1}"
TIMESTEPS="${2:-250000}"
CSV_PATH="../data/historical_1m.csv"

echo "🚀 Starting train → backtest workflow..."
echo "   Model: $MODEL_NAME"
echo "   Timesteps: $TIMESTEPS"
echo ""

# Step 1: Train
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📚 STEP 1: Training..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 train_backtest_rl_system.py train \
  --csv "$CSV_PATH" \
  --name "$MODEL_NAME" \
  --algo ppo \
  --timesteps "$TIMESTEPS"

if [ $? -ne 0 ]; then
  echo "❌ Training failed!"
  exit 1
fi

echo ""
echo "✅ Training complete!"
echo ""

# Step 2: Find the latest checkpoint (or latest_model alias)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 STEP 2: Finding latest checkpoint..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

LATEST_CHECKPOINT="./checkpoints/rl_training/${MODEL_NAME}_ppo/latest_model.zip"
if [ ! -f "$LATEST_CHECKPOINT" ]; then
  LATEST_CHECKPOINT=$(ls -t ./checkpoints/rl_training/"${MODEL_NAME}"_ppo/checkpoint_*.zip 2>/dev/null | head -1)
fi

if [ -z "$LATEST_CHECKPOINT" ]; then
  echo "❌ No checkpoint found!"
  exit 1
fi

echo "📁 Latest checkpoint: $LATEST_CHECKPOINT"
echo ""

# Step 3: Backtest
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📈 STEP 3: Backtesting..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

python3 train_backtest_rl_system.py backtest \
  --csv "$CSV_PATH" \
  --model "$LATEST_CHECKPOINT" \
  --algo ppo

if [ $? -ne 0 ]; then
  echo "❌ Backtest failed!"
  exit 1
fi

echo ""
echo "✅ All done! Train → Backtest workflow complete!"
