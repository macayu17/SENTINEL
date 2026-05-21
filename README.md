# SENTINEL

Smart Early-warning Network for Trading, Institutional orders, and Liquidity Events.

SENTINEL is a real-time market microstructure simulator with a FastAPI backend and a Next.js dashboard. It simulates order-book activity across multiple agent types, produces liquidity and large-order signals, and streams live updates over WebSockets to a terminal-style frontend.

## Stack

- Backend: Python 3.10, FastAPI, WebSockets
- Frontend: Next.js 15.5, TypeScript, Tailwind CSS, Zustand, Recharts
- Simulation: Multi-agent order-book engine with market maker, HFT, institutional, retail, informed, and noise agents
- Prediction: Liquidity shock scoring and large-order pattern detection
- Deployment: Vercel frontend + Azure App Service backend

## Repository Layout

```text
.
├── backend/
│   ├── src/
│   │   ├── agents/
│   │   ├── api/
│   │   ├── market/
│   │   ├── mcp/
│   │   ├── prediction/
│   │   └── utils/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── store/
│   ├── types/
│   └── .env.example
├── AZURE_APP_SERVICE.md
├── SENTINEL_PRD.md
└── docker-compose.yml
```

## Local Development

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn src.api.main:app --reload --port 8000
```

The backend can optionally load a trained market-making policy for the live simulator.
It supports:

- PPO models saved at `backend/models/ppo_market_maker.zip`
- Genetic-programming policies saved at `backend/models/gp_market_maker.json`

Use `RL_POLICY_KIND=ppo` or `RL_POLICY_KIND=gp` to choose which model format to run live.
PPO is disabled by default for deployment speed. To enable PPO locally, install the root `requirements.txt` or `backend/requirements-rl.txt`, then set `RL_POLICY_ENABLED=true`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Full Stack With Docker

```bash
docker-compose up --build
```

## Local URLs

- Dashboard: `http://localhost:3000/dashboard`
- Backend API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- WebSocket: `ws://localhost:8000/ws`

## Environment Files

### Backend

Copy `backend/.env.example` to `backend/.env` and adjust values if needed.

```text
SIMULATION_DURATION=23400
INITIAL_PRICE=100.0
RL_POLICY_ENABLED=false
RL_POLICY_KIND=ppo
RL_MODEL_PATH=models/ppo_market_maker.zip
HOST=0.0.0.0
PORT=8000
FRONTEND_URL=http://localhost:3000
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://localhost:3002,http://127.0.0.1:3002
GROWW_API_AUTH_TOKEN=
GROWW_API_KEY=
GROWW_API_SECRET=
GROWW_API_TOTP=
UPSTOX_ACCESS_TOKEN=
UPSTOX_ANALYTICS_TOKEN=
UPSTOX_BASE_URL=https://api.upstox.com/v3
UPSTOX_V2_BASE_URL=https://api.upstox.com/v2
```

For LIVE_SHADOW replay, keep Groww and Upstox credentials only in `backend/.env`.
Upstox historical candles, instrument search, and live LTP polling can use either a standard OAuth access token or a read-only Analytics Token:
set `UPSTOX_ACCESS_TOKEN` or `UPSTOX_ANALYTICS_TOKEN`, then use the Upstox tab to search/select an instrument key such as `NSE_EQ|INE002A01018`.

### Frontend

Copy `frontend/.env.example` to `frontend/.env.local`.

```text
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

## Backend API Overview

- `GET /api/health`
- `POST /api/simulation/start`
- `POST /api/simulation/stop`
- `POST /api/simulation/mode`
- `GET /api/prediction/liquidity`
- `GET /api/prediction/large-order`
- `GET /api/agents/metrics`
- `GET /api/market/snapshot`
- `POST /api/live-shadow/groww/fetch`
- `POST /api/live-shadow/groww/replay`
- `POST /api/live-shadow/upstox/fetch`
- `POST /api/live-shadow/upstox/replay`
- `GET /api/live-shadow/upstox/instruments`
- `POST /api/live-shadow/upstox/ltp`
- `POST /api/live-shadow/upstox/live`
- `WS /ws`

## Policy Training

Train PPO:

```bash
python train_rl.py --timesteps 60000 --save-path backend/models/ppo_market_maker
```

Train the genetic-programming baseline:

```bash
python train_gp.py --generations 8 --population-size 24 --save-path backend/models/gp_market_maker.json
```

## Notes About The Current Architecture

- The simulator state is stored in process memory, so production should run a single backend instance unless state is externalized.
- WebSocket streaming and the simulation loop both depend on a long-running backend process, so serverless backends are a poor fit.
- Stitch is treated as frontend/UI-only and is not part of the backend data pipeline.

## Deployment

### Frontend

- Host on Vercel
- Set:
  - `NEXT_PUBLIC_API_URL=https://<your-backend-domain>`
  - `NEXT_PUBLIC_WS_URL=wss://<your-backend-domain>`

### Backend

- Host on Azure App Service for Linux with the existing GitHub Actions zip workflow
- Set the startup command to `python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000`
- Enable App Service build automation so Azure installs `backend/requirements.txt`
- Set `FRONTEND_URL` and `ALLOWED_ORIGINS` to your Vercel production domain

Full Azure guide: [AZURE_APP_SERVICE.md](./AZURE_APP_SERVICE.md)

## Product Spec

The full product requirements doc is in [SENTINEL_PRD.md](./SENTINEL_PRD.md).
