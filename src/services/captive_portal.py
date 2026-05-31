"""
CaptivePortalService

In TOOLS_ONLY mode (default):
  - All devices on the AP get internet immediately -- no login wall.
  - The captive portal only protects access to Trarou tools at tra.rou
    (port 3000) and the admin API (port 8000).
  - OS captive-portal detection probes get a 204 / redirect response
    so the OS stops showing "Sign in to network" prompts.

In FULL mode (CAPTIVE_PORTAL_TOOLS_ONLY=False):
  - Classic captive portal: all HTTP is redirected to the splash page
    until the user authenticates.

The deinit-on-init bug was caused by dnsmasq receiving a SIGTERM because
the previous instance left a stale PID file.  Fixed by:
  - Always removing the PID file before starting.
  - Using --keep-in-foreground so the PID file race is avoided.
  - Starting dnsmasq with asyncio.create_subprocess_exec (not shell=True)
    so the process is tracked directly.
"""

import asyncio
import logging
from pathlib import Path

from config import settings

log = logging.getLogger(__name__)

DNSMASQ_CONF = "/tmp/trarou-dnsmasq.conf"
DNSMASQ_PID  = "/tmp/trarou-dnsmasq.pid"

# Captive-portal probe paths used by major OSes
CAPTIVE_PROBE_PATHS = [
    "/generate_204",
    "/connectivitycheck",
    "/hotspot-detect.html",
    "/success.txt",
    "/ncsi.txt",
    "/redirect",
]


class CaptivePortalService:

    _dnsmasq_proc: asyncio.subprocess.Process | None = None

    def _dnsmasq_conf(self) -> str:
        lines = [
            f"interface={settings.AP_INTERFACE}",
            "bind-interfaces",
            f"dhcp-range={settings.CAPTIVE_PORTAL_DHCP_START},{settings.CAPTIVE_PORTAL_DHCP_END},12h",
            f"dhcp-option=3,{settings.CAPTIVE_PORTAL_IP}",
            f"dhcp-option=6,{settings.CAPTIVE_PORTAL_IP}",
            f"pid-file={DNSMASQ_PID}",
            "no-resolv",
            "log-queries",
            "server=1.1.1.1",
            "server=8.8.8.8",
        ]

        if settings.CAPTIVE_PORTAL_TOOLS_ONLY:
            lines += [
                f"address=/{settings.TRAROU_HOSTNAME}/{settings.CAPTIVE_PORTAL_IP}",
                f"address=/trarou.local/{settings.CAPTIVE_PORTAL_IP}",
            ]
        else:
            lines.append(f"address=/#/{settings.CAPTIVE_PORTAL_IP}")

        return "\n".join(lines)

    async def _run(self, cmd: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await proc.communicate()
        return proc.returncode, out.decode().strip()

    async def start(self):
        # Fix: Remove stale PID file that caused immediate deinit
        pid_path = Path(DNSMASQ_PID)
        if pid_path.exists():
            try:
                old_pid = int(pid_path.read_text().strip())
                rc, out = await self._run(f"ps -p {old_pid} -o comm= 2>/dev/null")
                if "dnsmasq" in out:
                    await self._run(f"kill {old_pid} 2>/dev/null")
                    await asyncio.sleep(0.5)
            except Exception:
                pass
            pid_path.unlink(missing_ok=True)

        # Kill any other trarou-managed dnsmasq
        await self._run("pkill -f 'dnsmasq.*trarou' 2>/dev/null")
        await asyncio.sleep(0.3)

        # Write config
        Path(DNSMASQ_CONF).write_text(self._dnsmasq_conf())

        # Start dnsmasq -- use --keep-in-foreground so we track the process
        try:
            self._dnsmasq_proc = await asyncio.create_subprocess_exec(
                "dnsmasq",
                f"--conf-file={DNSMASQ_CONF}",
                "--keep-in-foreground",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.sleep(0.5)
            if self._dnsmasq_proc.returncode is not None:
                _, stderr = await self._dnsmasq_proc.communicate()
                log.error(f"dnsmasq exited immediately: {stderr.decode()}")
            else:
                log.info(f"dnsmasq started (pid={self._dnsmasq_proc.pid})")
        except FileNotFoundError:
            log.error("dnsmasq not found -- install it: apt install dnsmasq")
            return

        await self._setup_iptables()

    async def stop(self):
        if self._dnsmasq_proc and self._dnsmasq_proc.returncode is None:
            try:
                self._dnsmasq_proc.terminate()
                await asyncio.wait_for(self._dnsmasq_proc.wait(), timeout=5)
            except Exception:
                pass
        self._dnsmasq_proc = None
        await self._run("pkill -f 'dnsmasq.*trarou' 2>/dev/null")
        Path(DNSMASQ_PID).unlink(missing_ok=True)
        await self._teardown_iptables()

    async def _setup_iptables(self):
        iface  = settings.AP_INTERFACE
        ip     = settings.CAPTIVE_PORTAL_IP
        port   = settings.API_PORT
        subnet = settings.CAPTIVE_PORTAL_SUBNET

        rules = [
            "sysctl -w net.ipv4.ip_forward=1",
            f"iptables -t nat -A POSTROUTING -s {subnet} ! -d {subnet} -j MASQUERADE",
            f"iptables -A FORWARD -i {iface} -m state --state ESTABLISHED,RELATED -j ACCEPT",
            f"iptables -A FORWARD -i {iface} -j ACCEPT",
            "iptables -t nat -N TRAROU_PORTAL 2>/dev/null || true",
            f"iptables -t nat -A TRAROU_PORTAL -d {ip} -j RETURN",
        ]

        if settings.CAPTIVE_PORTAL_TOOLS_ONLY:
            pass  # No blanket HTTP redirect -- internet works freely
        else:
            rules += [
                f"iptables -t nat -A TRAROU_PORTAL -p tcp --dport 80 -j DNAT --to-destination {ip}:{port}",
                f"iptables -t nat -A TRAROU_PORTAL -p tcp --dport 443 -j DNAT --to-destination {ip}:{port}",
            ]

        rules.append(f"iptables -t nat -A PREROUTING -i {iface} -j TRAROU_PORTAL")

        for cmd in rules:
            rc, out = await self._run(cmd)
            if rc != 0:
                log.debug(f"iptables (may already exist): {cmd} -> {out}")

        log.info(f"iptables rules applied (tools_only={settings.CAPTIVE_PORTAL_TOOLS_ONLY})")

    async def _teardown_iptables(self):
        iface  = settings.AP_INTERFACE
        subnet = settings.CAPTIVE_PORTAL_SUBNET

        cmds = [
            f"iptables -t nat -D PREROUTING -i {iface} -j TRAROU_PORTAL 2>/dev/null",
            "iptables -t nat -F TRAROU_PORTAL 2>/dev/null",
            "iptables -t nat -X TRAROU_PORTAL 2>/dev/null",
            f"iptables -t nat -D POSTROUTING -s {subnet} ! -d {subnet} -j MASQUERADE 2>/dev/null",
            f"iptables -D FORWARD -i {iface} -j ACCEPT 2>/dev/null",
        ]
        for cmd in cmds:
            await self._run(cmd)
        log.info("iptables captive-portal rules removed.")
