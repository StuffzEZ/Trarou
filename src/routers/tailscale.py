"""
Tailscale router.

GET  /api/tailscale/status
POST /api/tailscale/up
POST /api/tailscale/down
POST /api/tailscale/set-exit-node
GET  /api/tailscale/peers
"""

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from routers.auth import get_current_admin
from services.tailscale import TailscaleService

log = logging.getLogger(__name__)
router = APIRouter()
AdminDep = Annotated[str, Depends(get_current_admin)]
_ts = TailscaleService()


@router.get("/status", summary="Tailscale daemon status")
async def tailscale_status(admin: AdminDep):
    try:
        if not await _ts.is_installed():
            return {"installed": False, "running": False,
                    "message": "Tailscale is not installed. Run: curl -fsSL https://tailscale.com/install.sh | sh"}
        status = await _ts.status()
        return {"installed": True, **status}
    except Exception as e:
        log.error(f"Tailscale status error: {e}")
        return {"installed": False, "running": False, "message": str(e)}


@router.post("/up", summary="Connect to Tailscale")
async def tailscale_up(
    admin: AdminDep,
    auth_key: Optional[str] = Body(default=None, embed=True),
    advertise_exit_node: bool = Body(default=False, embed=True),
):
    if not await _ts.is_installed():
        raise HTTPException(500, "Tailscale not installed")
    result = await _ts.up(auth_key=auth_key, advertise_exit_node=advertise_exit_node)
    return result


@router.post("/down", summary="Disconnect Tailscale")
async def tailscale_down(admin: AdminDep):
    if not await _ts.is_installed():
        raise HTTPException(500, "Tailscale not installed")
    return await _ts.down()


@router.post("/set-exit-node", summary="Route traffic through a Tailscale exit node")
async def set_exit_node(
    admin: AdminDep,
    ip: Optional[str] = Body(default=None, embed=True),
):
    return await _ts.set_exit_node(ip=ip)


@router.get("/peers", summary="List Tailscale peers")
async def tailscale_peers(admin: AdminDep):
    if not await _ts.is_installed():
        return {"peers": []}
    status = await _ts.status()
    return {"peers": status.get("peers", [])}
