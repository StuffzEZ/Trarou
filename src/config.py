"""
Trarou configuration -- reads from environment / .env file.
"""

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="/etc/trarou/trarou.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- General --------------------------------------------------------------
    API_PORT: int = 8000
    SECRET_KEY: str = secrets.token_hex(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720    # 12 hours

    # -- Admin credentials ----------------------------------------------------
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD_HASH: str = ""

    # -- Media ----------------------------------------------------------------
    MEDIA_BASE_DIR: str = ""
    MAX_UPLOAD_SIZE_MB: int = 2048

    @property
    def MEDIA_DIR(self) -> Path:
        if self.MEDIA_BASE_DIR:
            return Path(self.MEDIA_BASE_DIR)
        return Path.home() / "trarou-media"

    # -- Wi-Fi AP -------------------------------------------------------------
    AP_INTERFACE: str = "wlan0"
    AP_COUNTRY_CODE: str = "GB"
    AP_SSID: str = "Trarou"
    AP_CHANNEL: int = 6

    # If set, the AP requires a WPA2 password. Leave blank for open network
    # (captive portal handles authentication to Trarou tools).
    AP_PASSPHRASE: str = ""

    # -- Captive portal -------------------------------------------------------
    CAPTIVE_PORTAL_IP: str = "10.0.0.1"
    CAPTIVE_PORTAL_SUBNET: str = "10.0.0.0/24"
    CAPTIVE_PORTAL_DHCP_START: str = "10.0.0.10"
    CAPTIVE_PORTAL_DHCP_END: str = "10.0.0.200"

    # When True, the captive portal only gates access to Trarou tools
    # (tra.rou / port 3000). Internet and basic connectivity are always allowed.
    CAPTIVE_PORTAL_TOOLS_ONLY: bool = True

    FRONTEND_URL: str = "http://10.0.0.1:3000"
    # Short hostname alias served on the AP subnet
    TRAROU_HOSTNAME: str = "tra.rou"

    # -- noVNC ----------------------------------------------------------------
    VNC_HOST: str = "localhost"
    VNC_PORT: int = 5900
    NOVNC_PORT: int = 6080
    NOVNC_PATH: str = "/usr/share/novnc"

    # -- Wi-Fi client ---------------------------------------------------------
    CLIENT_INTERFACE: str = "wlan1"

    # -- Tailscale ------------------------------------------------------------
    TAILSCALE_ENABLED: bool = False

    # -- AI -------------------------------------------------------------------
    AI_ENABLED: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
