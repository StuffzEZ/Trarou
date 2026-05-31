"""
System router.

GET  /api/system/info        -- CPU, memory, disk, uptime
GET  /api/system/update-check -- check for updates on GitHub
POST /api/system/reboot      -- reboot the device (admin)
POST /api/system/shutdown    -- shut down the device (admin)
POST /api/system/set-password -- change admin password (admin)
"""

import asyncio
import json
import logging
import socket
import time
from pathlib import Path
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

VERSION_FILE = Path("/opt/trarou/backend/version.json")
GITHUB_REPO = "StuffzEZ/Trarou"


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


@router.get("/update-check", summary="Check for updates from GitHub")
async def update_check():
    """
    Compares local version with latest GitHub release.
    Returns current version, latest version, and whether an update is available.
    """
    # Read local version
    local_version = "unknown"
    if VERSION_FILE.exists():
        try:
            local_data = json.loads(VERSION_FILE.read_text())
            local_version = local_data.get("version", "unknown")
        except Exception:
            pass

    # Fetch latest release from GitHub
    try:
        loop = asyncio.get_event_loop()
        import urllib.request

        def fetch_latest():
            req = urllib.request.Request(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())

        latest = await loop.run_in_executor(None, fetch_latest)
        latest_version = latest.get("tag_name", "unknown").lstrip("v")
        download_url = None
        for asset in latest.get("assets", []):
            if asset.get("name", "").endswith(".zip"):
                download_url = asset.get("browser_download_url")
                break
        release_notes = latest.get("body", "")
    except Exception as e:
        log.warning(f"Failed to check for updates: {e}")
        return {
            "local_version": local_version,
            "latest_version": "unknown",
            "update_available": False,
            "error": "Could not reach GitHub",
        }

    # Compare versions
    update_available = False
    if local_version != "unknown" and latest_version != "unknown":
        try:
            local_parts = [int(x) for x in local_version.split(".")]
            latest_parts = [int(x) for x in latest_version.split(".")]
            update_available = latest_parts > local_parts
        except ValueError:
            update_available = local_version != latest_version

    return {
        "local_version": local_version,
        "latest_version": latest_version,
        "update_available": update_available,
        "download_url": download_url,
        "release_notes": release_notes,
    }


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
