#!/bin/bash
# Convenience wrapper for RL training/backtesting with common workflows

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
DATA_DIR="$BACKEND_DIR/data"
MODELS_DIR="$BACKEND_DIR/models"
CHECKPOINTS_DIR="$BACKEND_DIR/checkpoints"
RESULTS_DIR="$BACKEND_DIR/results"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
  echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
  echo -e "${BLUE}$1${NC}"
  echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
}

print_success() {
  echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
  echo -e "${RED}❌ $1${NC}"
}

print_warning() {
  echo -e "${YELLOW}⚠️  $1${NC}"
}

check_data() {
  if [ ! -f "$DATA_DIR/historical_1m.csv" ]; then
    print_error "No historical_1m.csv found in $DATA_DIR/"
    echo "Please upload your historical OHLCV data as: backend/data/historical_1m.csv"
    return 1
  fi
  print_success "Data file found: $DATA_DIR/historical_1m.csv"
  return 0
}

setup_dirs() {
  mkdir -p "$MODELS_DIR/rl_training"
  mkdir -p "$MODELS_DIR/rl_sweep"
  mkdir -p "$CHECKPOINTS_DIR/rl_training"
  mkdir -p "$CHECKPOINTS_DIR/rl_sweep"
  mkdir -p "$RESULTS_DIR/rl_training"
  mkdir -p "$RESULTS_DIR/rl_sweep"
  print_success "Directories ready"
}

cmd_train() {
  local name="${1:-ppo_intraday}"
  local algo="${2:-ppo}"
  local timesteps="${3:-250000}"
  local lr="${4:-3e-4}"
  local arch="${5:-256,256}"

  print_header "🚀 Training RL Model"
  echo "Name: $name"
  echo "Algorithm: $algo"
  echo "Timesteps: $timesteps"
  echo "Learning Rate: $lr"
  echo "Architecture: $arch"
  echo

  if ! check_data; then return 1; fi
  setup_dirs

  python "$BACKEND_DIR/scripts/train_backtest_rl_system.py" train \
    --csv "$DATA_DIR/historical_1m.csv" \
    --name "$name" \
    --algo "$algo" \
    --timesteps "$timesteps" \
    --lr "$lr" \
    --net-arch "$arch"

  print_success "Training complete!"
  echo "Model saved to: $MODELS_DIR/rl_training/${name}_${algo}"
}

cmd_backtest() {
  local model_name="${1}"
  local algo="${2:-ppo}"
  local timeframe="${3:-5min}"

  if [ -z "$model_name" ]; then
    print_error "Usage: $0 backtest <model_name> [algo] [timeframe]"
    return 1
  fi

  local model_path="$MODELS_DIR/rl_training/${model_name}_${algo}"

  if [ ! -d "$model_path" ]; then
    print_error "Model not found: $model_path"
    echo "Available models:"
    ls -1 "$MODELS_DIR/rl_training/" 2>/dev/null | sed 's/^/  - /'
    return 1
  fi

  print_header "📈 Backtesting Model"
  echo "Model: $model_name"
  echo "Algorithm: $algo"
  echo "Timeframe: $timeframe"
  echo

  if ! check_data; then return 1; fi
  setup_dirs

  python "$BACKEND_DIR/scripts/train_backtest_rl_system.py" backtest \
    --csv "$DATA_DIR/historical_1m.csv" \
    --model "$model_path" \
    --algo "$algo" \
    --timeframe "$timeframe"

  print_success "Backtest complete!"
  echo "Results saved to: $RESULTS_DIR/rl_training/"
}

cmd_sweep() {
  local force_fresh="${1:---no-force}"

  print_header "🔄 Hyperparameter Sweep"
  echo "Sweeping learning rates and network architectures"
  echo "Sweeps are resumable — you can safely interrupt (Ctrl+C) and re-run"
  echo

  if ! check_data; then return 1; fi
  setup_dirs

  if [ "$force_fresh" = "--force-fresh" ]; then
    print_warning "Clearing previous sweep results..."
    rm -rf "$CHECKPOINTS_DIR/rl_sweep/sweep_checkpoint.json"
  fi

  python "$BACKEND_DIR/scripts/train_backtest_rl_system.py" sweep \
    --csv "$DATA_DIR/historical_1m.csv" \
    --output-dir "$MODELS_DIR/rl_sweep" \
    --results-dir "$RESULTS_DIR/rl_sweep" \
    --checkpoint-dir "$CHECKPOINTS_DIR/rl_sweep" \
    $([ "$force_fresh" = "--force-fresh" ] && echo "--force-fresh")

  print_success "Sweep complete!"
  echo "Results saved to: $RESULTS_DIR/rl_sweep/sweep_results_*.json"
}

cmd_list() {
  print_header "📋 Available Models & Results"

  echo -e "\n${BLUE}Trained Models:${NC}"
  if [ -d "$MODELS_DIR/rl_training" ] && [ "$(ls -A "$MODELS_DIR/rl_training")" ]; then
    ls -1 "$MODELS_DIR/rl_training/" | sed 's/^/  ✓ /'
  else
    echo "  (none)"
  fi

  echo -e "\n${BLUE}Checkpoint Metadata:${NC}"
  if [ -f "$CHECKPOINTS_DIR/rl_training/checkpoint_metadata.json" ]; then
    cat "$CHECKPOINTS_DIR/rl_training/checkpoint_metadata.json" | python -m json.tool | head -20
  else
    echo "  (no checkpoints)"
  fi

  echo -e "\n${BLUE}Recent Results:${NC}"
  if [ -d "$RESULTS_DIR" ] && [ "$(find "$RESULTS_DIR" -type f -name '*.json' 2>/dev/null)" ]; then
    find "$RESULTS_DIR" -type f -name '*.json' -printf "%T@ %p\n" | sort -rn | head -5 | cut -d' ' -f2- | sed 's/^/  ✓ /'
  else
    echo "  (no results)"
  fi
}

cmd_cleanup() {
  print_warning "Cleaning up training files..."
  echo "This will remove:"
  echo "  - Old checkpoint files"
  echo "  - Tensorboard logs"
  echo "  - Temporary training data"
  echo

  read -p "Continue? (y/n) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "Cancelled"
    return 1
  fi

  rm -rf "$BACKEND_DIR/tensorboard_logs"/*
  rm -f "$CHECKPOINTS_DIR/rl_sweep/sweep_checkpoint.json"
  
  print_success "Cleanup complete!"
}

cmd_tensorboard() {
  local port="${1:-6006}"

  print_header "📊 Starting Tensorboard"
  echo "Log directory: $BACKEND_DIR/tensorboard_logs/"
  echo "View in browser: http://localhost:$port"
  echo

  tensorboard --logdir="$BACKEND_DIR/tensorboard_logs/" --port="$port"
}

cmd_help() {
  cat << EOF
RL Training & Backtesting Convenience Wrapper

Usage: $0 <command> [options]

Commands:

  train [name] [algo] [timesteps] [lr] [arch]
    Train a single RL model
    
    Options:
      name        Model name (default: ppo_intraday)
      algo        Algorithm: ppo|dqn (default: ppo)
      timesteps   Training steps (default: 250000)
      lr          Learning rate (default: 3e-4)
      arch        Network arch, e.g., "256,256" (default: 256,256)
    
    Examples:
      $0 train
      $0 train my_model ppo 100000 1e-4 256,256
      $0 train dqn_model dqn 250000 1e-4 128,128

  backtest <model_name> [algo] [timeframe]
    Backtest a trained model
    
    Options:
      model_name  ✓ REQUIRED: Name of trained model
      algo        Algorithm: ppo|dqn (default: ppo)
      timeframe   1min|5min|15min (default: 5min)
    
    Examples:
      $0 backtest ppo_intraday
      $0 backtest my_model ppo 5min
      $0 backtest dqn_model dqn 1min

  sweep [--force-fresh]
    Run hyperparameter sweep (resumable)
    
    Options:
      --force-fresh  Clear old checkpoint and restart
    
    Examples:
      $0 sweep
      $0 sweep --force-fresh

  list
    Show available models and results

  tensorboard [port]
    Start tensorboard dashboard
    
    Options:
      port  Port number (default: 6006)
    
    Examples:
      $0 tensorboard
      $0 tensorboard 8888

  cleanup
    Clean up training files (interactive)

  help
    Show this help message

Examples:

  # Quick start
  $0 train quick_test ppo 50000
  $0 backtest quick_test
  
  # Full workflow
  $0 train my_model ppo 250000 3e-4 256,256
  $0 backtest my_model ppo 5min
  
  # Hyperparameter search
  $0 sweep
  $0 train best_model ppo 500000 3e-4 256,256
  $0 backtest best_model ppo 5min
  
  # Monitor training
  $0 tensorboard 6006

EOF
}

# Main
main() {
  local cmd="${1:-help}"

  case "$cmd" in
    train)
      shift
      cmd_train "$@"
      ;;
    backtest)
      shift
      cmd_backtest "$@"
      ;;
    sweep)
      shift
      cmd_sweep "$@"
      ;;
    list)
      cmd_list
      ;;
    tensorboard)
      shift
      cmd_tensorboard "$@"
      ;;
    cleanup)
      cmd_cleanup
      ;;
    help|--help|-h)
      cmd_help
      ;;
    *)
      print_error "Unknown command: $cmd"
      echo "Run: $0 help"
      exit 1
      ;;
  esac
}

main "$@"
