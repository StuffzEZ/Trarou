"""
NetworkManagerService — wraps nmcli for Wi-Fi client operations.

All methods are async and safe to call from FastAPI route handlers.
"""

import asyncio
import logging
import re
from typing import Optional

from models.schemas import WifiNetwork

log = logging.getLogger(__name__)


class NetworkManagerService:

    async def _run(self, cmd: str) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode().strip(), stderr.decode().strip()

    # ── AP status ─────────────────────────────────────────────────────────────

    async def ap_is_active(self) -> bool:
        from config import settings
        rc, out, _ = await self._run(f"ip link show {settings.AP_INTERFACE} 2>/dev/null")
        return rc == 0 and "state UP" in out

    # ── Client status ─────────────────────────────────────────────────────────

    async def get_client_status(self) -> dict:
        from config import settings
        iface = settings.CLIENT_INTERFACE

        # Try nmcli first
        rc, out, _ = await self._run(
            f"nmcli -t -f DEVICE,TYPE,STATE,CONNECTION dev | grep '^{iface}:'"
        )
        if rc == 0 and out:
            parts = out.split(":")
            connected = len(parts) > 2 and parts[2] == "connected"
            ssid = parts[3] if len(parts) > 3 and connected else None

            ip = None
            if connected:
                rc2, out2, _ = await self._run(
                    f"nmcli -g IP4.ADDRESS dev show {iface}"
                )
                if rc2 == 0 and out2:
                    ip = out2.split("/")[0]

            return {"connected": connected, "ssid": ssid, "ip": ip}

        # Fallback: iwconfig
        rc, out, _ = await self._run(f"iwconfig {iface} 2>/dev/null")
        if rc == 0:
            ssid_match = re.search(r'ESSID:"([^"]+)"', out)
            connected = ssid_match is not None
            ssid = ssid_match.group(1) if ssid_match else None
            return {"connected": connected, "ssid": ssid, "ip": None}

        return {"connected": False, "ssid": None, "ip": None}

    # ── Scan ──────────────────────────────────────────────────────────────────

    async def scan_networks(self, iface: str) -> list[WifiNetwork]:
        # Trigger a rescan
        await self._run(f"nmcli dev wifi rescan ifname {iface} 2>/dev/null")
        await asyncio.sleep(2)

        rc, out, err = await self._run(
            f"nmcli -t -f SSID,SIGNAL,SECURITY,FREQ dev wifi list ifname {iface}"
        )

        networks: list[WifiNetwork] = []
        seen: set[str] = set()

        if rc != 0:
            log.warning(f"nmcli scan failed: {err}. Trying iwlist...")
            return await self._scan_iwlist(iface)

        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) < 4:
                continue
            ssid, signal_str, security, freq = parts[0], parts[1], parts[2], parts[3]
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            try:
                signal = int(signal_str)
            except ValueError:
                signal = -100
            networks.append(WifiNetwork(
                ssid=ssid,
                signal_strength=signal,
                security=security or "Open",
                frequency="5GHz" if "5" in freq else "2.4GHz",
            ))

        return sorted(networks, key=lambda n: -n.signal_strength)

    async def _scan_iwlist(self, iface: str) -> list[WifiNetwork]:
        rc, out, _ = await self._run(f"iwlist {iface} scan 2>/dev/null")
        networks: list[WifiNetwork] = []
        seen: set[str] = set()
        current_ssid = current_signal = current_security = None

        for line in out.splitlines():
            line = line.strip()
            if line.startswith("Cell "):
                if current_ssid and current_ssid not in seen:
                    networks.append(WifiNetwork(
                        ssid=current_ssid,
                        signal_strength=current_signal or -100,
                        security=current_security or "Open",
                        frequency="2.4GHz",
                    ))
                    seen.add(current_ssid)
                current_ssid = current_signal = current_security = None
            elif "ESSID:" in line:
                m = re.search(r'ESSID:"([^"]*)"', line)
                if m:
                    current_ssid = m.group(1)
            elif "Signal level=" in line:
                m = re.search(r'Signal level=(-?\d+)', line)
                if m:
                    current_signal = int(m.group(1))
            elif "WPA" in line or "WEP" in line:
                current_security = "WPA2" if "WPA2" in line else "WPA" if "WPA" in line else "WEP"

        # Append the last network
        if current_ssid and current_ssid not in seen:
            networks.append(WifiNetwork(
                ssid=current_ssid,
                signal_strength=current_signal or -100,
                security=current_security or "Open",
                frequency="2.4GHz",
            ))

        return sorted(networks, key=lambda n: -n.signal_strength)

    # ── Connect / disconnect ──────────────────────────────────────────────────

    async def connect(self, iface: str, ssid: str, password: Optional[str]) -> tuple[bool, str]:
        import shlex
        # Sanitize inputs to prevent shell injection
        safe_ssid = shlex.quote(ssid)
        safe_iface = shlex.quote(iface)
        if password:
            safe_pass = shlex.quote(password)
            cmd = f'nmcli dev wifi connect {safe_ssid} password {safe_pass} ifname {safe_iface}'
        else:
            cmd = f'nmcli dev wifi connect {safe_ssid} ifname {safe_iface}'

        rc, out, err = await self._run(cmd)
        if rc == 0:
            log.info(f"Connected to {ssid} on {iface}")
            return True, out
        log.warning(f"Failed to connect to {ssid}: {err}")
        return False, err

    async def disconnect(self, iface: str) -> tuple[bool, str]:
        import shlex
        rc, out, err = await self._run(f"nmcli dev disconnect {shlex.quote(iface)}")
        if rc == 0:
            return True, out
        return False, err
