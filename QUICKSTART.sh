#!/bin/bash
# Quick-start checks for the current SENTINEL tree.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

echo "=========================================="
echo "SENTINEL Quick Start"
echo "=========================================="
echo ""

echo "Step 1: Backend tests"
echo "------------------------------------------"
cd "$SCRIPT_DIR"
python -m pytest -q backend/tests
echo "[ok] Backend tests passed"
echo ""

echo "Step 2: Frontend lint and build"
echo "------------------------------------------"
cd "$FRONTEND_DIR"
npm run lint
npm run build
echo "[ok] Frontend checks passed"
echo ""

echo "Step 3: Optional RL setup check"
echo "------------------------------------------"
cd "$SCRIPT_DIR"
if command -v bash >/dev/null 2>&1 && { command -v python >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1; }; then
  bash "$SCRIPT_DIR/verify_rl_setup.sh" || echo "[warning] Optional RL setup check did not pass; install the reported packages before training."
else
  echo "[skip] bash/Python is not available; run verify_rl_setup.sh from Git Bash or WSL."
fi

echo ""
echo "=========================================="
echo "Run Locally"
echo "=========================================="
echo "Backend:"
echo "  cd $BACKEND_DIR"
echo "  python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "Frontend:"
echo "  cd $FRONTEND_DIR"
echo "  npm run dev"
echo ""
echo "Dashboard:"
echo "  http://localhost:3000/dashboard"
echo ""
echo "RL training help:"
echo "  ./rl_train.sh help"
