"""
Trarou configuration — reads from environment / .env file.
"""

import os
import secrets
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="/etc/trarou/trarou.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── General ──────────────────────────────────────────────────────────────
    API_PORT: int = 8000
    SECRET_KEY: str = secrets.token_hex(32)   # override in production .env
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720    # 12 hours

    # ── Admin credentials (set via /etc/trarou/trarou.env) ───────────────────
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD_HASH: str = ""             # bcrypt hash; set at install time

    # ── Media ─────────────────────────────────────────────────────────────────
    MEDIA_BASE_DIR: str = ""                  # default = /home/<current user>/trarou-media
    MAX_UPLOAD_SIZE_MB: int = 2048

    @property
    def MEDIA_DIR(self) -> Path:
        if self.MEDIA_BASE_DIR:
            return Path(self.MEDIA_BASE_DIR)
        home = Path.home()
        return home / "trarou-media"

    # ── Wi-Fi AP ──────────────────────────────────────────────────────────────
    AP_INTERFACE: str = "wlan0"               # built-in adapter
    AP_COUNTRY_CODE: str = "GB"               # regulatory domain for hostapd
    AP_SSID: str = "Trarou"
    AP_CHANNEL: int = 6
    AP_PASSPHRASE: str = ""                   # empty = open network (captive portal handles auth)

    # ── Captive portal ────────────────────────────────────────────────────────
    CAPTIVE_PORTAL_IP: str = "10.0.0.1"
    CAPTIVE_PORTAL_SUBNET: str = "10.0.0.0/24"
    CAPTIVE_PORTAL_DHCP_START: str = "10.0.0.10"
    CAPTIVE_PORTAL_DHCP_END: str = "10.0.0.200"
    FRONTEND_URL: str = "http://10.0.0.1:3000"  # where the SvelteKit/React app runs

    # ── noVNC ─────────────────────────────────────────────────────────────────
    VNC_HOST: str = "localhost"
    VNC_PORT: int = 5900
    NOVNC_PORT: int = 6080
    NOVNC_PATH: str = "/usr/share/novnc"

    # ── Wi-Fi client ─────────────────────────────────────────────────────────
    CLIENT_INTERFACE: str = "wlan1"           # external USB adapter for upstream connectivity


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
