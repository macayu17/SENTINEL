#!/bin/bash
# Verify RL Training System setup

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
SETUP_OK=1

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}================================================================${NC}"
echo -e "${BLUE}RL Training System - Setup Verification${NC}"
echo -e "${BLUE}================================================================${NC}\n"

# Check Python
echo -n "[check] Python... "
if command -v python &> /dev/null; then
    PYTHON_BIN="python"
elif command -v python3 &> /dev/null; then
    PYTHON_BIN="python3"
else
    echo -e "${RED}NOT FOUND${NC}"
    exit 1
fi

PYTHON_VERSION=$("$PYTHON_BIN" --version 2>&1)
echo -e "${GREEN}$PYTHON_VERSION${NC}"

# Check required files
echo -n "[check] Main training script... "
if [ -f "$BACKEND_DIR/scripts/train_backtest_rl_system.py" ]; then
    echo -e "${GREEN}Found${NC}"
else
    echo -e "${RED}NOT FOUND${NC}"
    exit 1
fi

echo -n "[check] Bash wrapper... "
if [ -f "$SCRIPT_DIR/rl_train.sh" ] && [ -x "$SCRIPT_DIR/rl_train.sh" ]; then
    echo -e "${GREEN}Found (executable)${NC}"
else
    echo -e "${RED}NOT FOUND or not executable${NC}"
    exit 1
fi

# Check documentation
echo -n "[check] Documentation... "
DOCS=("RL_QUICK_START.md" "RL_TRAINING_GUIDE.md" "SETUP_RL_TRAINING.md")
MISSING=()
for doc in "${DOCS[@]}"; do
    if [ ! -f "$SCRIPT_DIR/$doc" ]; then
        MISSING+=("$doc")
    fi
done

if [ ${#MISSING[@]} -eq 0 ]; then
    echo -e "${GREEN}All docs found${NC}"
else
    echo -e "${YELLOW}Missing: ${MISSING[*]}${NC}"
fi

# Check Python syntax
echo -n "[check] Python syntax... "
if "$PYTHON_BIN" -m py_compile "$BACKEND_DIR/scripts/train_backtest_rl_system.py" 2>/dev/null; then
    echo -e "${GREEN}Valid${NC}"
else
    echo -e "${RED}SYNTAX ERROR${NC}"
    exit 1
fi

# Check directories
echo -n "[check] Checking/creating directories... "
mkdir -p "$BACKEND_DIR/data"
mkdir -p "$BACKEND_DIR/models/rl_training"
mkdir -p "$BACKEND_DIR/checkpoints/rl_training"
mkdir -p "$BACKEND_DIR/results/rl_training"
mkdir -p "$BACKEND_DIR/tensorboard_logs"
echo -e "${GREEN}OK${NC}"

# Check imports
echo -n "[check] Required Python packages... "
PACKAGES=("stable_baselines3" "gymnasium" "pandas" "numpy")
MISSING_PACKAGES=()
for pkg in "${PACKAGES[@]}"; do
    if ! "$PYTHON_BIN" -c "import $pkg" 2>/dev/null; then
        MISSING_PACKAGES+=("$pkg")
    fi
done

if [ ${#MISSING_PACKAGES[@]} -eq 0 ]; then
    echo -e "${GREEN}All found${NC}"
else
    echo -e "${YELLOW}Missing: ${MISSING_PACKAGES[*]}${NC}"
    echo "Install with: $PYTHON_BIN -m pip install ${MISSING_PACKAGES[*]}"
    SETUP_OK=0
fi

# Summary
echo -e "\n${BLUE}================================================================${NC}"
if [ "$SETUP_OK" -eq 1 ]; then
    echo -e "${GREEN}[ok] Setup verification complete${NC}\n"
else
    echo -e "${YELLOW}[warning] Setup verification found missing dependencies${NC}\n"
fi

echo "Directory structure:"
echo "  Data dir:          $BACKEND_DIR/data/"
echo "  Models dir:        $BACKEND_DIR/models/rl_training/"
echo "  Checkpoints dir:   $BACKEND_DIR/checkpoints/rl_training/"
echo "  Results dir:       $BACKEND_DIR/results/rl_training/"
echo "  Tensorboard logs:  $BACKEND_DIR/tensorboard_logs/"

echo -e "\n${BLUE}Quick Start:${NC}"
echo "  1. Upload data: cp data.csv $BACKEND_DIR/data/historical_1m.csv"
echo "  2. Train:       $SCRIPT_DIR/rl_train.sh train test ppo 50000"
echo "  3. Backtest:    $SCRIPT_DIR/rl_train.sh backtest test"
echo "  4. Help:        $SCRIPT_DIR/rl_train.sh help"

echo -e "\n${BLUE}Documentation:${NC}"
echo "  - Quick Reference:  $SCRIPT_DIR/RL_QUICK_START.md"
echo "  - Setup Guide:      $SCRIPT_DIR/SETUP_RL_TRAINING.md"
echo "  - Full Manual:      $SCRIPT_DIR/RL_TRAINING_GUIDE.md"
echo "  - Summary:          $SCRIPT_DIR/RL_SYSTEM_SUMMARY.md"

echo -e "\n${BLUE}================================================================${NC}"
if [ "$SETUP_OK" -eq 1 ]; then
    echo -e "${GREEN}Ready to start training!${NC}\n"
else
    echo -e "${YELLOW}Install the missing packages before training.${NC}\n"
    exit 1
fi
