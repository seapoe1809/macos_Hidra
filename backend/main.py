"""Hidra FastAPI application entry point.

Run from the repo root (hidra/) — usually via the `./darnahi` launcher, or:
    hvenv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000

Serves the JSON API under /api/* and the static JS frontend at /.
"""

import os
import time
from collections import defaultdict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend import config, db
from backend.routers import (
    enroll, messaging, provider, identity, audit, wallets, qr, contracts, payments, bills,
)

app = FastAPI(title="Darnahi · Project Hidra", version="0.3.0")

# CORS is opt-in: the SPA is served same-origin, so by default no cross-origin
# access is granted. Only enable the middleware if origins were configured.
if config.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# --- Brute-force throttle for auth-sensitive endpoints ---------------------
# Lightweight in-memory sliding window per client IP. Good enough for a single
# process; front a real limiter (nginx / slowapi+redis) for multi-worker.
_RL_WINDOW = 60.0            # seconds
_RL_MAX = 15                 # requests per window per IP
_RL_PATHS = ("/api/provider/login",)
_rl_hits: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def rate_limit_and_headers(request: Request, call_next):
    path = request.url.path
    if path in _RL_PATHS:
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        hits = [t for t in _rl_hits[ip] if now - t < _RL_WINDOW]
        if len(hits) >= _RL_MAX:
            return JSONResponse(
                {"detail": "Too many attempts. Try again shortly."}, status_code=429
            )
        hits.append(now)
        _rl_hits[ip] = hits

    response = await call_next(request)
    # Baseline security headers on every response.
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


@app.on_event("startup")
def _startup():
    config.warn_on_insecure_config()
    db.init_db()


@app.get("/api/health")
def health():
    return {"status": "ok", "hub_npub": config.HUB_NPUB, "relays": config.RELAYS}


# API routers
app.include_router(enroll.router)
app.include_router(messaging.router)
app.include_router(provider.router)
app.include_router(identity.router)
app.include_router(audit.router)
app.include_router(wallets.router)
app.include_router(qr.router)
app.include_router(contracts.router)
app.include_router(payments.router)
app.include_router(bills.router)

# Static frontend (mounted last so it doesn't shadow /api/*).
if os.path.isdir(config.FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
