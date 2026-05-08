# Azure Backend Deployment

This repo is set up for a **Vercel frontend** and an **Azure App Service for Linux backend** deployed from the GitHub Actions zip workflow in `.github/workflows/main_sentinel.yml`.

## Recommended Topology

- Frontend: Vercel
- Backend: Azure App Service for Linux, Python 3.10
- Frontend URL example: `https://sentinel-app.vercel.app`
- Backend URL example: `https://sentinel-api.azurewebsites.net`

The backend keeps simulator state and WebSocket clients in process, so keep the backend instance count at `1`.

## Azure App Settings

Set these in Azure App Service Configuration:

```text
SCM_DO_BUILD_DURING_DEPLOYMENT=true
ENABLE_ORYX_BUILD=true
FRONTEND_URL=https://your-vercel-domain.vercel.app
ALLOWED_ORIGINS=https://your-vercel-domain.vercel.app
SIMULATION_DURATION=23400
INITIAL_PRICE=100.0
RL_POLICY_ENABLED=false
RL_POLICY_KIND=ppo
RL_MODEL_PATH=models/ppo_market_maker.zip
```

Startup command:

```text
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

The PPO model lives under `backend/models/ppo_market_maker.zip`, which is packaged into the backend zip as `models/ppo_market_maker.zip`. PPO stays disabled in the default Azure zip deploy because the heavy `stable-baselines3` stack is intentionally excluded from `backend/requirements.txt`; enable it only after adding that optional dependency path to your deployment build.

## Azure Portal Steps

1. Create an App Service:
   - Publish: `Code`
   - Runtime stack: `Python 3.10`
   - Operating system: `Linux`
2. In Configuration, add the app settings listed above.
3. In Configuration > General settings, set the startup command shown above.
4. Enable WebSockets.
5. Set Health check path to `/api/health`.
6. Keep scale-out instance count at `1`.
7. Make sure the GitHub Actions workflow secrets referenced in `.github/workflows/main_sentinel.yml` are present.
8. Push to `main` or run the workflow manually.

## Frontend Setup On Vercel

Set these environment variables in Vercel:

```text
NEXT_PUBLIC_API_URL=https://<your-app>.azurewebsites.net
NEXT_PUBLIC_WS_URL=wss://<your-app>.azurewebsites.net
```

Use the backend origin only. Do not append `/api` or `/ws`.

## Docker

`backend/Dockerfile` and `docker-compose.yml` are for local/container smoke testing. They are not the current GitHub Actions deployment path.

## Operational Notes

- Restarting the backend resets the in-memory simulation state.
- Scaling beyond one backend instance needs externalized simulator state and WebSocket fanout.
- If CORS fails, verify the exact Vercel production domain in both `FRONTEND_URL` and `ALLOWED_ORIGINS`.
