"""
Trarou Backend - Travel Router Software
Main FastAPI application entry point.
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from fastapi.responses import RedirectResponse
from starlette.requests import Request

from routers import auth, media, network, system, vnc
from services.captive_portal import CaptivePortalService
from services.hostapd import HostapdService
from services.network_manager import NetworkManagerService
from config import settings

# ── Logging ──────────────────────────────────────────────────────────────────
import os
os.makedirs("/var/log/trarou", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/var/log/trarou/trarou.log"),
    ],
)
log = logging.getLogger("trarou")


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=== Trarou starting up ===")

    # Ensure media directory exists
    settings.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    log.info(f"Media directory: {settings.MEDIA_DIR}")

    # Start AP + captive portal
    hostapd = HostapdService()
    captive = CaptivePortalService()
    try:
        await hostapd.start()
        await captive.start()
        log.info("Access point and captive portal are up.")
    except Exception as e:
        log.warning(f"AP/captive portal startup issue (may need root): {e}")

    yield

    log.info("=== Trarou shutting down ===")
    try:
        await hostapd.stop()
        await captive.stop()
    except Exception:
        pass


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Trarou",
    description="Travel Router Backend API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # credentials require explicit origins; use False with wildcard
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router,    prefix="/api/auth",    tags=["auth"])
app.include_router(media.router,   prefix="/api/media",   tags=["media"])
app.include_router(network.router, prefix="/api/network", tags=["network"])
app.include_router(system.router,  prefix="/api/system",  tags=["system"])
app.include_router(vnc.router,     prefix="/api/vnc",     tags=["vnc"])

# Serve the trarou-media folder so the frontend can stream/download files
app.mount(
    "/media-files",
    StaticFiles(directory=str(settings.MEDIA_DIR), check_dir=False),
    name="media-files",
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


# ── Captive portal splash redirect ──────────────────────────────────────────
# OS captive-portal checks (connectivitycheck.gstatic.com, captive.apple.com, etc.)
# get DNS → 10.0.0.1, then iptables DNATs port 80 → API port 8000.
# Redirect them to the frontend so the user sees the login page.


@app.get("/", include_in_schema=False)
async def splash_root():
    return RedirectResponse(url=settings.FRONTEND_URL)


@app.api_route("/{path:path}", methods=["GET", "HEAD"])
async def captive_portal_catch_all(path: str, request: Request):
    # Don't redirect API calls or media streams
    if path.startswith("api/") or path.startswith("media-files/") or path.startswith("docs"):
        from fastapi import HTTPException
        raise HTTPException(404)
    return RedirectResponse(url=settings.FRONTEND_URL)


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=settings.API_PORT,
        reload=False,
        log_level="info",
    )
