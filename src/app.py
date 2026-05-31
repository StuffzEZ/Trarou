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
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from config import settings
from routers import auth, media, network, system, vnc
from routers import ai as ai_router
from routers import settings as settings_router
from routers import shortcuts as shortcuts_router
from routers import tailscale as tailscale_router
from services.captive_portal import CaptivePortalService, CAPTIVE_PROBE_PATHS
from services.hostapd import HostapdService

# -- Logging -----------------------------------------------------------------
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

_hostapd = HostapdService()
_captive  = CaptivePortalService()


# -- Lifespan ----------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=== Trarou starting up ===")
    settings.MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    try:
        await _hostapd.start()
        await _captive.start()
        log.info("Access point and captive portal are up.")
    except Exception as e:
        log.warning(f"AP/captive portal startup issue (may need root): {e}")

    # Start Tailscale routing if it was previously enabled
    if settings.TAILSCALE_ENABLED:
        try:
            from services.tailscale import TailscaleService
            ts = TailscaleService()
            if await ts.is_installed():
                status = await ts.status()
                if status.get("running"):
                    await ts._setup_ts_routing()
                    log.info("Tailscale routing re-enabled.")
        except Exception as e:
            log.warning(f"Tailscale startup: {e}")

    yield

    log.info("=== Trarou shutting down ===")
    try:
        await _hostapd.stop()
        await _captive.stop()
    except Exception:
        pass


# -- App ---------------------------------------------------------------------
app = FastAPI(
    title="Trarou",
    description="Travel Router Backend API",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Routers -----------------------------------------------------------------
app.include_router(auth.router,             prefix="/api/auth",       tags=["auth"])
app.include_router(media.router,            prefix="/api/media",      tags=["media"])
app.include_router(network.router,          prefix="/api/network",    tags=["network"])
app.include_router(system.router,           prefix="/api/system",     tags=["system"])
app.include_router(vnc.router,              prefix="/api/vnc",        tags=["vnc"])
app.include_router(ai_router.router,        prefix="/api/ai",         tags=["ai"])
app.include_router(settings_router.router,  prefix="/api/settings",   tags=["settings"])
app.include_router(shortcuts_router.router, prefix="/api/shortcuts",  tags=["shortcuts"])
app.include_router(tailscale_router.router, prefix="/api/tailscale",  tags=["tailscale"])

# Media file serving
app.mount(
    "/media-files",
    StaticFiles(directory=str(settings.MEDIA_DIR), check_dir=False),
    name="media-files",
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.1.0"}


# -- Captive portal probe handling -------------------------------------------
@app.get("/generate_204")
@app.get("/connectivitycheck.gstatic.com/generate_204")
async def captive_204():
    if settings.CAPTIVE_PORTAL_TOOLS_ONLY:
        return Response(status_code=204)
    return RedirectResponse(url=settings.FRONTEND_URL)


@app.get("/hotspot-detect.html")
async def captive_apple():
    if settings.CAPTIVE_PORTAL_TOOLS_ONLY:
        return HTMLResponse("<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>")
    return RedirectResponse(url=settings.FRONTEND_URL)


@app.get("/success.txt")
@app.get("/ncsi.txt")
async def captive_windows_firefox():
    if settings.CAPTIVE_PORTAL_TOOLS_ONLY:
        return Response(content="Microsoft NCSI" if "ncsi" in "/ncsi.txt" else "success\n",
                        media_type="text/plain")
    return RedirectResponse(url=settings.FRONTEND_URL)


# -- tra.rou / root redirect -------------------------------------------------
@app.get("/", include_in_schema=False)
async def splash_root(request: Request):
    host = request.headers.get("host", "")
    if settings.TRAROU_HOSTNAME in host or "trarou.local" in host:
        return RedirectResponse(url=settings.FRONTEND_URL)
    return RedirectResponse(url=settings.FRONTEND_URL)


@app.api_route("/{path:path}", methods=["GET", "HEAD"])
async def catch_all(path: str, request: Request):
    if any(path.startswith(p) for p in ["api/", "media-files/", "docs", "openapi"]):
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
