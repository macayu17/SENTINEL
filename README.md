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
│   │   ├── data/
│   │   ├── market/
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
HOST=0.0.0.0
PORT=8000
FRONTEND_URL=http://localhost:3000
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://localhost:3002,http://127.0.0.1:3002
```

### Frontend

Copy `frontend/.env.example` to `frontend/.env.local`.

```text
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

## Liquidity Depth Collection

Set `UPSTOX_ANALYTICS_TOKEN` in `backend/.env`, then record read-only five-level
depth snapshots:

```bash
python backend/scripts/record_upstox_depth.py
```

By default the recorder loads the fixed 20-stock universe in
`backend/config/liquidity_universe.v1.json`. It contains 7 high, 7 medium, and
6 lower-liquidity NSE equities, ranked by median daily traded value over the
documented 33-session measurement window. Manual `--instrument-key` arguments
override the universe. Use `--samples 60` for a bounded check. Data is appended
to ignored JSONL files under `backend/data/liquidity_depth/`.

The recorder only calls Upstox's full-market-quote GET endpoint. It does not
place, modify, or cancel orders. Recorded data does not enable the trained
liquidity predictor until a future-shock label definition and out-of-time model
evaluation pass are completed.

After collecting at least ten full market sessions, build and evaluate a
candidate:

```bash
python backend/scripts/train_liquidity_model.py
```

Features use only the previous five minutes. A positive label requires at least
two spread-expansion or depth-collapse observations in the following 60 seconds.
Sessions are split chronologically, probabilities are calibrated, and candidates
must beat ROC-AUC, average-precision, and Brier-score gates. Failed runs write a
report but never create or replace the active runtime model.

## Backend API Overview

- `GET /api/health`
- `POST /api/simulation/stop`
- `GET /api/simulation/export`
- `POST /api/sandbox/create`
- `GET /api/sandbox/presets`
- `GET /api/sandbox/scenarios`
- `WS /ws`

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
