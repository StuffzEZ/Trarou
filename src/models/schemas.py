"""
Trarou shared Pydantic models.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# -- Auth ---------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    is_admin: bool = False

class CaptiveLoginRequest(BaseModel):
    username: str
    password: str
    mac: Optional[str] = None


# -- Media --------------------------------------------------------------------

class MediaFile(BaseModel):
    name: str
    path: str
    url: str
    size_bytes: int
    mime_type: str
    modified_at: datetime

class MediaFolder(BaseModel):
    name: str
    path: str
    children_count: int

class MediaTree(BaseModel):
    folders: list[MediaFolder]
    files: list[MediaFile]
    total_files: int
    total_size_bytes: int


# -- Network ------------------------------------------------------------------

class WifiNetwork(BaseModel):
    ssid: str
    signal_strength: int
    security: str
    frequency: str

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


# -- System -------------------------------------------------------------------

class SystemInfo(BaseModel):
    hostname: str
    uptime_seconds: int
    cpu_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_used_gb: float
    disk_total_gb: float
    load_avg: list[float]


# -- VNC ----------------------------------------------------------------------

class VncStatus(BaseModel):
    running: bool
    novnc_url: Optional[str] = None
    vnc_port: int
    novnc_port: int


# -- Tailscale ----------------------------------------------------------------

class TailscalePeer(BaseModel):
    hostname: str
    dns_name: str
    ips: list[str]
    online: bool
    exit_node: bool
    os: str

class TailscaleStatus(BaseModel):
    installed: bool
    running: bool
    hostname: Optional[str] = None
    ips: list[str] = []
    exit_node_active: bool = False
    peers: list[TailscalePeer] = []


# -- AI -----------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str

class KnowledgeEntry(BaseModel):
    id: str
    title: str
    content: str


# -- Settings (for the configurable web interface) ----------------------------

class SettingsUpdate(BaseModel):
    """Subset of settings that can be changed at runtime via the web UI."""
    AP_SSID: Optional[str] = None
    AP_PASSPHRASE: Optional[str] = None
    AP_CHANNEL: Optional[int] = None
    AP_COUNTRY_CODE: Optional[str] = None
    CAPTIVE_PORTAL_TOOLS_ONLY: Optional[bool] = None
    FRONTEND_URL: Optional[str] = None
    MAX_UPLOAD_SIZE_MB: Optional[int] = None
    TAILSCALE_ENABLED: Optional[bool] = None
    AI_ENABLED: Optional[bool] = None
