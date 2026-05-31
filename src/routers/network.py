"""
Network router.

GET  /api/network/status           — AP + client interface status
GET  /api/network/scan             — scan for nearby Wi-Fi networks
POST /api/network/connect          — connect client iface to an upstream network
POST /api/network/disconnect       — disconnect client iface
GET  /api/network/ap               — AP configuration
POST /api/network/ap/restart       — restart the access point
"""

import asyncio
import logging
import re
import socket
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from config import settings
from models.schemas import NetworkStatus, WifiConnectRequest, WifiNetwork
from routers.auth import get_current_admin
from services.network_manager import NetworkManagerService

log = logging.getLogger(__name__)
router = APIRouter()
AdminDep = Annotated[str, Depends(get_current_admin)]
_nm = NetworkManagerService()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _run(cmd: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode().strip(), stderr.decode().strip()


async def _check_internet() -> bool:
    try:
        loop = asyncio.get_event_loop()
        def check():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(3)
            try:
                s.connect(("1.1.1.1", 53))
                s.close()
                return True
            except Exception:
                s.close()
                return False
        return await loop.run_in_executor(None, check)
    except Exception:
        return False


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status", response_model=NetworkStatus, summary="Current network status")
async def network_status():
    ap_active = await _nm.ap_is_active()
    client_info = await _nm.get_client_status()
    internet = await _check_internet()

    return NetworkStatus(
        ap_interface=settings.AP_INTERFACE,
        ap_ssid=settings.AP_SSID,
        ap_active=ap_active,
        client_interface=settings.CLIENT_INTERFACE,
        client_connected=client_info.get("connected", False),
        client_ssid=client_info.get("ssid"),
        client_ip=client_info.get("ip"),
        internet_reachable=internet,
    )


@router.get("/scan", summary="Scan for nearby Wi-Fi networks (admin)")
async def scan_networks(admin: AdminDep):
    """
    Triggers an iwlist/nmcli scan and returns nearby SSIDs.
    """
    networks = await _nm.scan_networks(settings.CLIENT_INTERFACE)
    return {"networks": networks}


@router.post("/connect", summary="Connect client interface to an upstream network (admin)")
async def connect_network(admin: AdminDep, req: WifiConnectRequest):
    """
    Connects the client (non-AP) interface to an upstream Wi-Fi network.
    Uses nmcli under the hood.
    """
    success, msg = await _nm.connect(settings.CLIENT_INTERFACE, req.ssid, req.password)
    if not success:
        raise HTTPException(500, detail=f"Connection failed: {msg}")
    return {"status": "connected", "ssid": req.ssid}


@router.post("/disconnect", summary="Disconnect client interface (admin)")
async def disconnect_network(admin: AdminDep):
    success, msg = await _nm.disconnect(settings.CLIENT_INTERFACE)
    if not success:
        raise HTTPException(500, detail=f"Disconnect failed: {msg}")
    return {"status": "disconnected"}


@router.get("/ap", summary="Access point configuration")
async def get_ap_config(admin: AdminDep):
    return {
        "interface": settings.AP_INTERFACE,
        "ssid": settings.AP_SSID,
        "channel": settings.AP_CHANNEL,
        "ip": settings.CAPTIVE_PORTAL_IP,
        "subnet": settings.CAPTIVE_PORTAL_SUBNET,
    }


@router.post("/ap/restart", summary="Restart the access point (admin)")
async def restart_ap(admin: AdminDep):
    from services.hostapd import HostapdService
    svc = HostapdService()
    await svc.stop()
    await asyncio.sleep(1)
    await svc.start()
    return {"status": "ap restarted"}
