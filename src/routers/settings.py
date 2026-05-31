"""
Settings router -- allows viewing and changing Trarou configuration
via the web interface without SSH.

GET  /api/settings
POST /api/settings
POST /api/settings/restart-ap
"""

import logging
import re
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException

from config import settings, get_settings
from models.schemas import SettingsUpdate
from routers.auth import get_current_admin

log = logging.getLogger(__name__)
router = APIRouter()
AdminDep = Annotated[str, Depends(get_current_admin)]

ENV_FILE = "/etc/trarou/trarou.env"

AP_RESTART_KEYS = {"AP_SSID", "AP_PASSPHRASE", "AP_CHANNEL", "AP_COUNTRY_CODE"}


def _read_env() -> dict[str, str]:
    try:
        with open(ENV_FILE) as f:
            result = {}
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    result[k.strip()] = v.strip()
            return result
    except FileNotFoundError:
        return {}


def _write_env(data: dict[str, str]):
    try:
        existing = _read_env()
        existing.update(data)
        lines = [f"{k}={v}\n" for k, v in existing.items()]
        with open(ENV_FILE, "w") as f:
            f.writelines(lines)
        get_settings.cache_clear()
    except PermissionError:
        raise HTTPException(500, f"Cannot write {ENV_FILE} -- check permissions")


@router.get("", summary="Get current configuration (admin)")
async def get_config(admin: AdminDep):
    env = _read_env()
    masked = {}
    for k, v in env.items():
        if "PASSWORD" in k or "SECRET" in k or "KEY" in k or "HASH" in k:
            masked[k] = "------" if v else ""
        else:
            masked[k] = v

    return {
        "settings": masked,
        "editable": {
            "AP_SSID": settings.AP_SSID,
            "AP_PASSPHRASE": "------" if settings.AP_PASSPHRASE else "",
            "AP_CHANNEL": settings.AP_CHANNEL,
            "AP_COUNTRY_CODE": settings.AP_COUNTRY_CODE,
            "CAPTIVE_PORTAL_TOOLS_ONLY": settings.CAPTIVE_PORTAL_TOOLS_ONLY,
            "FRONTEND_URL": settings.FRONTEND_URL,
            "MAX_UPLOAD_SIZE_MB": settings.MAX_UPLOAD_SIZE_MB,
            "TAILSCALE_ENABLED": settings.TAILSCALE_ENABLED,
            "AI_ENABLED": settings.AI_ENABLED,
            "AP_INTERFACE": settings.AP_INTERFACE,
            "CLIENT_INTERFACE": settings.CLIENT_INTERFACE,
            "CAPTIVE_PORTAL_IP": settings.CAPTIVE_PORTAL_IP,
        }
    }


@router.post("", summary="Update configuration (admin)")
async def update_config(admin: AdminDep, updates: SettingsUpdate):
    changed = {k: v for k, v in updates.model_dump().items() if v is not None}
    if not changed:
        return {"status": "no changes"}

    if "AP_CHANNEL" in changed:
        ch = changed["AP_CHANNEL"]
        if ch not in list(range(1, 15)) + list(range(36, 166, 4)):
            raise HTTPException(400, f"Invalid channel: {ch}")

    if "AP_COUNTRY_CODE" in changed:
        cc = changed["AP_COUNTRY_CODE"]
        if not re.match(r'^[A-Z]{2}$', cc):
            raise HTTPException(400, "Country code must be 2 uppercase letters")

    if "AP_SSID" in changed:
        ssid = changed["AP_SSID"]
        if not ssid or len(ssid) > 32:
            raise HTTPException(400, "SSID must be 1-32 characters")

    env_updates = {k: str(v) for k, v in changed.items()}
    _write_env(env_updates)

    needs_ap_restart = bool(AP_RESTART_KEYS & set(changed.keys()))
    log.info(f"Settings updated by {admin}: {list(changed.keys())}")

    return {
        "status": "updated",
        "changed": list(changed.keys()),
        "needs_ap_restart": needs_ap_restart,
    }


@router.post("/restart-ap", summary="Restart the access point (admin)")
async def restart_ap(admin: AdminDep):
    from services.hostapd import HostapdService
    from services.captive_portal import CaptivePortalService

    get_settings.cache_clear()

    hostapd = HostapdService()
    captive = CaptivePortalService()

    log.info(f"AP restart requested by {admin}")
    await captive.stop()
    await hostapd.stop()
    import asyncio
    await asyncio.sleep(1)
    await hostapd.start()
    await captive.start()

    return {"status": "ap restarted", "ssid": settings.AP_SSID}
