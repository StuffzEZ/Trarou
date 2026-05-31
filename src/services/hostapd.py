"""
HostapdService -- manages the hostapd access point.

Bug fix: The init/deinit cycle was caused by:
  1. hostapd being called while NetworkManager still had the interface.
  2. A race between `ip link set up` and hostapd binding.
  3. Stale PID files from previous runs.

Fixes applied:
  - Wait for NM to actually release the interface before starting hostapd.
  - Add a short stabilisation delay after `ip link set up`.
  - Remove stale PID file before starting.
  - Track the process handle so stop() sends to the right PID.
  - On failure, log the full hostapd output so the cause is visible.
"""

import asyncio
import logging
import os
import textwrap
from pathlib import Path

from config import settings

log = logging.getLogger(__name__)

HOSTAPD_CONF = "/etc/trarou/trarou-hostapd.conf"
HOSTAPD_PID  = "/var/run/trarou-hostapd.pid"


class HostapdService:

    _proc: asyncio.subprocess.Process | None = None

    def _build_conf(self) -> str:
        base = textwrap.dedent(f"""\
            interface={settings.AP_INTERFACE}
            driver=nl80211
            ssid={settings.AP_SSID}
            hw_mode=g
            channel={settings.AP_CHANNEL}
            macaddr_acl=0
            ignore_broadcast_ssid=0
            country_code={settings.AP_COUNTRY_CODE}
            ieee80211n=1
            wmm_enabled=1
        """)

        if settings.AP_PASSPHRASE:
            # Passphrase is stored in env file with 600 permissions
            # hostapd requires it in this config file
            base += textwrap.dedent(f"""\
                auth_algs=1
                wpa=2
                wpa_passphrase={settings.AP_PASSPHRASE}
                wpa_key_mgmt=WPA-PSK
                rsn_pairwise=CCMP
            """)
        else:
            base += "auth_algs=1\n"

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
        """Tell NetworkManager to release the interface and wait until it does."""
        await self._run(f"nmcli device set {iface} managed no 2>/dev/null")
        for _ in range(6):
            rc, out = await self._run(
                f"nmcli -t -f DEVICE,STATE dev | grep '^{iface}:'"
            )
            if "unmanaged" in out or rc != 0:
                break
            await asyncio.sleep(0.5)

    async def start(self):
        iface = settings.AP_INTERFACE

        # Clean up any stale state
        pid_path = Path(HOSTAPD_PID)
        if pid_path.exists():
            try:
                old_pid = int(pid_path.read_text().strip())
                rc, out = await self._run(f"ps -p {old_pid} -o comm= 2>/dev/null")
                if "hostapd" in out:
                    os.kill(old_pid, 15)
                    await asyncio.sleep(1)
            except Exception:
                pass
            pid_path.unlink(missing_ok=True)

        # Kill any other hostapd on this interface
        await self._run(f"pkill -f 'hostapd.*{iface}' 2>/dev/null")
        await asyncio.sleep(0.5)

        # Release interface from NetworkManager
        await self._unmanage_nm(iface)

        # Bring interface down, set AP mode, then up
        await self._run(f"ip link set {iface} down 2>/dev/null")
        await asyncio.sleep(0.2)
        await self._run(f"iw dev {iface} set type ap 2>/dev/null")
        await self._run(f"ip addr flush dev {iface} 2>/dev/null")
        await self._run(
            f"ip addr add {settings.CAPTIVE_PORTAL_IP}/24 dev {iface} 2>/dev/null"
        )
        await self._run(f"ip link set {iface} up 2>/dev/null")

        # Give the driver time to stabilise
        await asyncio.sleep(0.8)

        # Write hostapd config with restrictive permissions (atomic create)
        Path(HOSTAPD_CONF).parent.mkdir(parents=True, exist_ok=True)
        config_content = self._build_conf()
        fd = os.open(HOSTAPD_CONF, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(config_content)
        log.info(f"hostapd config: SSID={settings.AP_SSID}, "
                 f"passphrase={'set' if settings.AP_PASSPHRASE else 'open'}")

        # Start hostapd -- track the process directly to avoid PID-file races
        try:
            self._proc = await asyncio.create_subprocess_exec(
                "hostapd", HOSTAPD_CONF,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            log.error("hostapd not found -- install it: apt install hostapd")
            return

        # Give hostapd ~2 s to bind and start beaconing
        for _ in range(8):
            await asyncio.sleep(0.25)
            if self._proc.returncode is not None:
                _, stderr = await self._proc.communicate()
                log.error(f"hostapd exited (code {self._proc.returncode}): {stderr.decode()}")
                self._proc = None
                return

        log.info(f"hostapd started (pid={self._proc.pid}, iface={iface})")

    async def stop(self):
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
                log.info("hostapd stopped.")
            except Exception as e:
                log.warning(f"hostapd stop error: {e}")
        self._proc = None

        # Belt-and-suspenders
        pid_path = Path(HOSTAPD_PID)
        if pid_path.exists():
            try:
                pid = int(pid_path.read_text().strip())
                os.kill(pid, 15)
            except Exception:
                pass
            pid_path.unlink(missing_ok=True)

        await self._run(f"pkill -f 'hostapd.*trarou' 2>/dev/null")
