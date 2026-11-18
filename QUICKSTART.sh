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
npm test
npm run build
echo "[ok] Frontend checks passed"
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
