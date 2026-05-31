"""
Trarou shared Pydantic models.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    is_admin: bool = False

class CaptiveLoginRequest(BaseModel):
    """Used by the captive-portal splash page."""
    username: str
    password: str
    mac: Optional[str] = None     # client MAC passed by the portal redirect


# ── Media ─────────────────────────────────────────────────────────────────────

class MediaFile(BaseModel):
    name: str
    path: str           # relative path inside trarou-media
    url: str            # absolute URL to stream/download the file
    size_bytes: int
    mime_type: str
    modified_at: datetime

class MediaFolder(BaseModel):
    name: str
    path: str           # relative path inside trarou-media
    children_count: int

class MediaTree(BaseModel):
    folders: list[MediaFolder]
    files: list[MediaFile]
    total_files: int
    total_size_bytes: int


# ── Network ───────────────────────────────────────────────────────────────────

class WifiNetwork(BaseModel):
    ssid: str
    signal_strength: int    # dBm
    security: str           # WPA2, WPA3, Open …
    frequency: str          # 2.4GHz / 5GHz

class WifiConnectRequest(BaseModel):
    ssid: str
    password: Optional[str] = None

class NetworkStatus(BaseModel):
    ap_interface: str
    ap_ssid: str
    ap_active: bool
    client_interface: str
    client_connected: bool
    client_ssid: Optional[str] = None
    client_ip: Optional[str] = None
    internet_reachable: bool


# ── System ────────────────────────────────────────────────────────────────────

class SystemInfo(BaseModel):
    hostname: str
    uptime_seconds: int
    cpu_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_used_gb: float
    disk_total_gb: float
    load_avg: list[float]


# ── VNC ───────────────────────────────────────────────────────────────────────

class VncStatus(BaseModel):
    running: bool
    novnc_url: Optional[str] = None
    vnc_port: int
    novnc_port: int
