# SENTINEL

Smart Early-warning Network for Trading, Institutional orders, and Liquidity Events.

SENTINEL is a real-time market microstructure simulator with a FastAPI backend and a Next.js dashboard. It simulates order-book activity across multiple agent types, produces liquidity and large-order signals, and streams live updates over WebSockets to a terminal-style frontend.

## Stack

- Backend: Python 3.10, FastAPI, WebSockets
- Frontend: Next.js 14, TypeScript, Tailwind CSS, Zustand, Recharts
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
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

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

- Host on Azure App Service (Linux, custom container)
- Use the existing `backend/Dockerfile`
- Set `WEBSITES_PORT=8000`
- Set `FRONTEND_URL` and `ALLOWED_ORIGINS` to your Vercel production domain

Full Azure guide: [AZURE_APP_SERVICE.md](./AZURE_APP_SERVICE.md)

## Product Spec

The full product requirements doc is in [SENTINEL_PRD.md](./SENTINEL_PRD.md).
