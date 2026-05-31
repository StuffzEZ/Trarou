"""
System router.

GET  /api/system/info        — CPU, memory, disk, uptime
POST /api/system/reboot      — reboot the device (admin)
POST /api/system/shutdown    — shut down the device (admin)
POST /api/system/set-password — change admin password (admin)
"""

import asyncio
import logging
import socket
import time
from typing import Annotated

import bcrypt
import psutil
from fastapi import APIRouter, Body, Depends, HTTPException

from config import settings, get_settings
from models.schemas import SystemInfo
from routers.auth import get_current_admin

log = logging.getLogger(__name__)
router = APIRouter()
AdminDep = Annotated[str, Depends(get_current_admin)]


@router.get("/info", response_model=SystemInfo, summary="Hardware / OS info")
async def system_info():
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    uptime = int(time.time() - psutil.boot_time())
    load = list(psutil.getloadavg())

    return SystemInfo(
        hostname=socket.gethostname(),
        uptime_seconds=uptime,
        cpu_percent=psutil.cpu_percent(interval=0.5),
        memory_used_mb=mem.used / 1024 / 1024,
        memory_total_mb=mem.total / 1024 / 1024,
        disk_used_gb=disk.used / 1024 ** 3,
        disk_total_gb=disk.total / 1024 ** 3,
        load_avg=load,
    )


@router.post("/reboot", summary="Reboot device (admin)")
async def reboot(admin: AdminDep):
    log.warning(f"REBOOT requested by {admin}")
    asyncio.create_task(_delayed_reboot())
    return {"status": "rebooting in 3 seconds"}


@router.post("/shutdown", summary="Shutdown device (admin)")
async def shutdown(admin: AdminDep):
    log.warning(f"SHUTDOWN requested by {admin}")
    asyncio.create_task(_delayed_shutdown())
    return {"status": "shutting down in 3 seconds"}


@router.post("/set-password", summary="Change admin password (admin)")
async def set_password(
    admin: AdminDep,
    new_password: str = Body(..., embed=True, min_length=8),
):
    """
    Hashes and persists the new password into /etc/trarou/trarou.env.
    """
    hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    env_path = "/etc/trarou/trarou.env"
    try:
        try:
            with open(env_path, "r") as f:
                lines = f.readlines()
        except FileNotFoundError:
            lines = []

        # Replace or append the hash line
        new_lines = [l for l in lines if not l.startswith("ADMIN_PASSWORD_HASH=")]
        new_lines.append(f"ADMIN_PASSWORD_HASH={hashed}\n")

        with open(env_path, "w") as f:
            f.writelines(new_lines)

        # Invalidate settings cache
        get_settings.cache_clear()
        log.info("Admin password updated.")
        return {"status": "password updated"}
    except PermissionError:
        raise HTTPException(500, "Cannot write /etc/trarou/trarou.env — check permissions")


# ── Internal ──────────────────────────────────────────────────────────────────

async def _delayed_reboot():
    await asyncio.sleep(3)
    proc = await asyncio.create_subprocess_shell("reboot")
    await proc.communicate()


async def _delayed_shutdown():
    await asyncio.sleep(3)
    proc = await asyncio.create_subprocess_shell("shutdown -h now")
    await proc.communicate()
