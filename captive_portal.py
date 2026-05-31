"""
CaptivePortalService

Sets up:
  1. dnsmasq — DHCP server on the AP interface + DNS that points everything
               to the router IP (for captive-portal detection).
  2. iptables — NAT rules that redirect all HTTP traffic from unauthorised
               clients to the splash page on port 8000.

Requires root / CAP_NET_ADMIN + CAP_NET_RAW.
"""

import asyncio
import logging
import textwrap
from pathlib import Path

from config import settings

log = logging.getLogger(__name__)

DNSMASQ_CONF = "/tmp/trarou-dnsmasq.conf"
DNSMASQ_PID  = "/tmp/trarou-dnsmasq.pid"


class CaptivePortalService:

    # ── dnsmasq ───────────────────────────────────────────────────────────────

    def _dnsmasq_conf(self) -> str:
        return textwrap.dedent(f"""
            interface={settings.AP_INTERFACE}
            bind-interfaces
            dhcp-range={settings.CAPTIVE_PORTAL_DHCP_START},{settings.CAPTIVE_PORTAL_DHCP_END},12h
            dhcp-option=3,{settings.CAPTIVE_PORTAL_IP}     # default gateway
            dhcp-option=6,{settings.CAPTIVE_PORTAL_IP}     # DNS server
            # Redirect all DNS queries to us so captive-portal detection fires
            address=/#/{settings.CAPTIVE_PORTAL_IP}
            no-resolv
            log-queries
            pid-file={DNSMASQ_PID}
        """).strip()

    async def _run(self, cmd: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await proc.communicate()
        return proc.returncode, out.decode().strip()

    async def start(self):
        # Write dnsmasq config
        Path(DNSMASQ_CONF).write_text(self._dnsmasq_conf())

        rc, out = await self._run(f"dnsmasq --conf-file={DNSMASQ_CONF}")
        if rc != 0:
            log.error(f"dnsmasq failed: {out}")
        else:
            log.info("dnsmasq (DHCP + DNS) started.")

        await self._setup_iptables()

    async def stop(self):
        await self._run("pkill -f 'dnsmasq.*trarou' 2>/dev/null")
        await self._teardown_iptables()

    # ── iptables ──────────────────────────────────────────────────────────────

    async def _setup_iptables(self):
        iface  = settings.AP_INTERFACE
        ip     = settings.CAPTIVE_PORTAL_IP
        port   = settings.API_PORT
        subnet = settings.CAPTIVE_PORTAL_SUBNET

        rules = [
            # Enable IP forwarding
            "sysctl -w net.ipv4.ip_forward=1",

            # NAT: masquerade outbound traffic from AP subnet
            f"iptables -t nat -A POSTROUTING -s {subnet} -j MASQUERADE",

            # Allow established connections
            f"iptables -A FORWARD -i {iface} -m state --state ESTABLISHED,RELATED -j ACCEPT",

            # --- Captive portal chain ---
            "iptables -t nat -N TRAROU_PORTAL 2>/dev/null || true",

            # Don't redirect traffic already destined for us (API / noVNC)
            f"iptables -t nat -A TRAROU_PORTAL -d {ip} -j RETURN",

            # Redirect HTTP to our API splash page
            f"iptables -t nat -A TRAROU_PORTAL -p tcp --dport 80 -j DNAT --to-destination {ip}:{port}",
            f"iptables -t nat -A TRAROU_PORTAL -p tcp --dport 443 -j DNAT --to-destination {ip}:{port}",

            # Jump to portal chain for all traffic from AP
            f"iptables -t nat -A PREROUTING -i {iface} -j TRAROU_PORTAL",
        ]

        for cmd in rules:
            rc, out = await self._run(cmd)
            if rc != 0:
                log.debug(f"iptables rule (may already exist): {cmd} → {out}")

        log.info("iptables captive-portal rules applied.")

    async def _teardown_iptables(self):
        iface  = settings.AP_INTERFACE
        subnet = settings.CAPTIVE_PORTAL_SUBNET

        cmds = [
            f"iptables -t nat -D PREROUTING -i {iface} -j TRAROU_PORTAL 2>/dev/null",
            "iptables -t nat -F TRAROU_PORTAL 2>/dev/null",
            "iptables -t nat -X TRAROU_PORTAL 2>/dev/null",
            f"iptables -t nat -D POSTROUTING -s {subnet} -j MASQUERADE 2>/dev/null",
        ]
        for cmd in cmds:
            await self._run(cmd)
        log.info("iptables captive-portal rules removed.")
