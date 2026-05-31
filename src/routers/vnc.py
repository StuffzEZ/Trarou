"""
VNC / noVNC router.

GET  /api/vnc/status      — is noVNC running?
POST /api/vnc/start       — launch noVNC websockify proxy (admin)
POST /api/vnc/stop        — kill noVNC process (admin)
GET  /api/vnc/url         — return the noVNC launch URL (admin)
"""

import asyncio
import logging
import os
import signal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from config import settings
from models.schemas import VncStatus
from routers.auth import get_current_admin

log = logging.getLogger(__name__)
router = APIRouter()
AdminDep = Annotated[str, Depends(get_current_admin)]

_novnc_process: asyncio.subprocess.Process | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _novnc_url() -> str:
    return (
        f"http://{settings.CAPTIVE_PORTAL_IP}:{settings.NOVNC_PORT}/vnc.html"
        f"?host={settings.CAPTIVE_PORTAL_IP}"
        f"&port={settings.NOVNC_PORT}"
        f"&autoconnect=true"
        f"&resize=scale"
    )


def _is_running() -> bool:
    global _novnc_process
    return _novnc_process is not None and _novnc_process.returncode is None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status", response_model=VncStatus, summary="noVNC status")
async def vnc_status(admin: AdminDep):
    running = _is_running()
    return VncStatus(
        running=running,
        novnc_url=_novnc_url() if running else None,
        vnc_port=settings.VNC_PORT,
        novnc_port=settings.NOVNC_PORT,
    )


@router.post("/start", response_model=VncStatus, summary="Start noVNC proxy (admin)")
async def vnc_start(admin: AdminDep):
    """
    Launches websockify to bridge noVNC (WebSocket) → VNC (TCP).
    Requires:
      - A VNC server running on localhost:5900 (e.g. tigervnc, x11vnc)
      - noVNC installed at NOVNC_PATH
      - websockify available in PATH
    """
    global _novnc_process

    if _is_running():
        return VncStatus(running=True, novnc_url=_novnc_url(), vnc_port=settings.VNC_PORT, novnc_port=settings.NOVNC_PORT)

    novnc_web = settings.NOVNC_PATH
    cmd = (
        f"websockify --web {novnc_web} "
        f"0.0.0.0:{settings.NOVNC_PORT} "
        f"{settings.VNC_HOST}:{settings.VNC_PORT}"
    )
    log.info(f"Starting noVNC: {cmd}")
    try:
        _novnc_process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # Give it a moment to bind
        await asyncio.sleep(0.8)
        if _novnc_process.returncode is not None:
            raise RuntimeError("websockify exited immediately — check VNC server and noVNC path")
    except FileNotFoundError:
        raise HTTPException(500, "websockify not found — install it with: pip install websockify")
    except Exception as e:
        raise HTTPException(500, str(e))

    log.info(f"noVNC started on port {settings.NOVNC_PORT}")
    return VncStatus(running=True, novnc_url=_novnc_url(), vnc_port=settings.VNC_PORT, novnc_port=settings.NOVNC_PORT)


@router.post("/stop", summary="Stop noVNC proxy (admin)")
async def vnc_stop(admin: AdminDep):
    global _novnc_process
    if not _is_running():
        return {"status": "not running"}
    try:
        _novnc_process.send_signal(signal.SIGTERM)
        await asyncio.wait_for(_novnc_process.wait(), timeout=5)
    except Exception as e:
        log.warning(f"Error stopping noVNC: {e}")
    _novnc_process = None
    log.info("noVNC stopped.")
    return {"status": "stopped"}


@router.get("/url", summary="Get the noVNC launch URL (admin)")
async def vnc_url(admin: AdminDep):
    return {"url": _novnc_url(), "running": _is_running()}
