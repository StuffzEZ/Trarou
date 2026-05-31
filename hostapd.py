"""
HostapdService — manages the hostapd access point.

Creates /tmp/trarou-hostapd.conf at runtime and starts/stops the daemon.
Requires hostapd to be installed and the process to have root (or CAP_NET_ADMIN).
"""

import asyncio
import logging
import os
import textwrap
from pathlib import Path

from config import settings

log = logging.getLogger(__name__)

HOSTAPD_CONF = "/tmp/trarou-hostapd.conf"
HOSTAPD_PID  = "/tmp/trarou-hostapd.pid"


class HostapdService:

    def _build_conf(self) -> str:
        base = textwrap.dedent(f"""
            interface={settings.AP_INTERFACE}
            driver=nl80211
            ssid={settings.AP_SSID}
            hw_mode=g
            channel={settings.AP_CHANNEL}
            macaddr_acl=0
            ignore_broadcast_ssid=0
            country_code={settings.AP_COUNTRY_CODE}
        """).strip()

        if settings.AP_PASSPHRASE:
            base += textwrap.dedent(f"""
                auth_algs=1
                wpa=2
                wpa_passphrase={settings.AP_PASSPHRASE}
                wpa_key_mgmt=WPA-PSK
                rsn_pairwise=CCMP
            """)
        else:
            # Open network — captive portal handles auth
            base += "\nauth_algs=1\n"

        return base

    async def _run(self, cmd: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await proc.communicate()
        return proc.returncode, out.decode().strip()

    async def _unmanage_nm(self, iface: str):
        """Tell NetworkManager to ignore an interface so it doesn't fight hostapd."""
        await self._run(f"nmcli device set {iface} managed no 2>/dev/null")

    async def start(self):
        iface = settings.AP_INTERFACE

        # Tell NetworkManager to leave this interface alone
        await self._unmanage_nm(iface)

        # Kill anything already using the interface
        await self._run(f"ip link set {iface} down 2>/dev/null")
        await self._run(f"iw dev {iface} set type ap 2>/dev/null")

        # Write config
        conf = self._build_conf()
        Path(HOSTAPD_CONF).write_text(conf)
        log.info(f"hostapd config written to {HOSTAPD_CONF}")

        # Assign static IP to AP interface
        rc, out = await self._run(f"ip addr add {settings.CAPTIVE_PORTAL_IP}/24 dev {iface} 2>/dev/null; ip link set {iface} up")
        log.debug(f"ip addr: {out}")

        # Start hostapd
        rc, out = await self._run(
            f"hostapd -B -P {HOSTAPD_PID} {HOSTAPD_CONF}"
        )
        if rc != 0:
            log.error(f"hostapd failed to start: {out}")
        else:
            log.info("hostapd started.")

    async def stop(self):
        pid_file = Path(HOSTAPD_PID)
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 15)   # SIGTERM
                pid_file.unlink(missing_ok=True)
                log.info("hostapd stopped.")
            except Exception as e:
                log.warning(f"Could not stop hostapd: {e}")
        else:
            rc, _ = await self._run("pkill -f 'hostapd.*trarou' 2>/dev/null")
