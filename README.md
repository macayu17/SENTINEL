# SENTINEL

**Smart Early-warning Network for Trading, Institutional orders, and Liquidity Events**

Real-time market microstructure simulator with ML-powered liquidity shock prediction, large order detection, and a Bloomberg-terminal-style dashboard.

## Quick Start

### Backend (Local Dev)

```bash
cd backend
pip install -r requirements.txt
uvicorn src.api.main:app --reload --port 8000
```

### Frontend (Local Dev)

```bash
cd frontend
npm install
npm run dev
```

### Docker (Full Stack)

```bash
docker-compose up --build
```

## URLs

- **Dashboard:** http://localhost:3000/dashboard
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **WebSocket:** ws://localhost:8000/ws

## Architecture

- **Backend:** Python 3.10 + FastAPI — multi-agent order book simulation, ML prediction, WebSocket streaming
- **Frontend:** Next.js 14 + TypeScript + Tailwind CSS — Bloomberg terminal-style real-time dashboard
- **Agents:** MarketMaker, HFT, Institutional, Retail, Informed, Noise
- **ML:** RandomForest liquidity shock predictor, Iceberg/TWAP large order detector

## Train ML Models

```bash
cd backend
python -c "
from src.prediction.liquidity_shock import LiquidityShockPredictor
p = LiquidityShockPredictor()
data = p.generate_training_data(num_simulations=50)
p.train(data)
"
```
