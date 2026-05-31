"""
TailscaleService -- manages Tailscale VPN so every device on the Trarou AP
shares a single Tailscale node.

Flow:
  1. Tailscale daemon runs on the Pi.
  2. AP clients are NATted through the Pi's tailscale0 interface.
  3. Split DNS: Trarou dnsmasq forwards *.ts.net queries to 100.100.100.100
     (MagicDNS), everything else goes to the upstream resolver.
"""

import asyncio
import json
import logging
import re
from typing import Optional

log = logging.getLogger(__name__)


class TailscaleService:

    async def _run(self, cmd: str) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode().strip(), stderr.decode().strip()

    async def status(self) -> dict:
        rc, out, err = await self._run("tailscale status --json 2>/dev/null")
        if rc != 0:
            return {"running": False, "error": err or "tailscale not running"}

        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            return {"running": False, "error": "could not parse tailscale status"}

        self_node = data.get("Self", {})
        peers = []
        for key, peer in data.get("Peer", {}).items():
            peers.append({
                "hostname": peer.get("HostName", ""),
                "dns_name": peer.get("DNSName", ""),
                "ips": peer.get("TailscaleIPs", []),
                "online": peer.get("Online", False),
                "exit_node": peer.get("ExitNode", False),
                "exit_node_option": peer.get("ExitNodeOption", False),
                "os": peer.get("OS", ""),
            })

        backend_state = data.get("BackendState", "")
        authenticated = backend_state == "Running"

        return {
            "running": authenticated,
            "backend_state": backend_state,
            "hostname": self_node.get("HostName", ""),
            "dns_name": self_node.get("DNSName", ""),
            "ips": self_node.get("TailscaleIPs", []),
            "exit_node_active": bool(data.get("ExitNodeStatus")),
            "exit_node_ip": (data.get("ExitNodeStatus") or {}).get("TailscaleIPs", [None])[0],
            "peers": peers,
        }

    async def up(self, auth_key: Optional[str] = None, advertise_routes: bool = True,
                 accept_routes: bool = True, advertise_exit_node: bool = False) -> dict:
        import shlex
        from config import settings

        flags = []
        if auth_key:
            # Validate auth key format (alphanumeric + hyphens only)
            import re
            if not re.match(r'^[a-zA-Z0-9\-]+$', auth_key):
                return {"status": "error", "message": "Invalid auth key format"}
            flags.append(f"--authkey={shlex.quote(auth_key)}")
        if accept_routes:
            flags.append("--accept-routes")
        if advertise_exit_node:
            flags.append("--advertise-exit-node")

        if advertise_routes:
            subnet = settings.CAPTIVE_PORTAL_SUBNET
            flags.append(f"--advertise-routes={shlex.quote(subnet)}")

        await self._run("sysctl -w net.ipv4.ip_forward=1")
        await self._run("sysctl -w net.ipv6.conf.all.forwarding=1")

        cmd = "tailscale up " + " ".join(flags) + " 2>&1"
        rc, out, err = await self._run(cmd)

        login_url = None
        for line in (out + err).splitlines():
            if "https://login.tailscale.com" in line or "https://tailscale.com" in line:
                match = re.search(r'https://login\.tailscale\.com/\S+', line)
                if not match:
                    match = re.search(r'https://tailscale\.com/\S+', line)
                if match:
                    url = match.group(0).rstrip('.')
                    # Validate URL format
                    if re.match(r'^https://(login\.)?tailscale\.com/[a-zA-Z0-9/_\-?=&%]+$', url):
                        login_url = url
                        break

        if login_url:
            return {"status": "needs_auth", "login_url": login_url}

        if rc == 0 or "already" in out.lower():
            await self._setup_ts_routing()
            return {"status": "connected"}

        return {"status": "error", "message": out or err}

    async def down(self) -> dict:
        await self._teardown_ts_routing()
        rc, out, err = await self._run("tailscale down 2>&1")
        if rc == 0:
            return {"status": "disconnected"}
        return {"status": "error", "message": err}

    async def set_exit_node(self, ip: Optional[str] = None) -> dict:
        import shlex
        import re
        if ip:
            # Validate IP format
            if not re.match(r'^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$', ip):
                return {"status": "error", "message": "Invalid IP address format"}
            rc, out, err = await self._run(f"tailscale set --exit-node={shlex.quote(ip)} --exit-node-allow-lan-access")
        else:
            rc, out, err = await self._run("tailscale set --exit-node=")

        if rc == 0:
            return {"status": "ok", "exit_node": ip}
        return {"status": "error", "message": err}

    async def _setup_ts_routing(self):
        from config import settings
        subnet = settings.CAPTIVE_PORTAL_SUBNET
        ap_iface = settings.AP_INTERFACE

        rules = [
            f"iptables -A FORWARD -i {ap_iface} -o tailscale0 -j ACCEPT",
            f"iptables -A FORWARD -i tailscale0 -o {ap_iface} -m state --state ESTABLISHED,RELATED -j ACCEPT",
            f"iptables -t nat -A POSTROUTING -s {subnet} -o tailscale0 -j MASQUERADE",
        ]
        for cmd in rules:
            await self._run(cmd + " 2>/dev/null || true")
        log.info("Tailscale iptables routing enabled for AP subnet.")

    async def _teardown_ts_routing(self):
        from config import settings
        subnet = settings.CAPTIVE_PORTAL_SUBNET
        ap_iface = settings.AP_INTERFACE

        cmds = [
            f"iptables -D FORWARD -i {ap_iface} -o tailscale0 -j ACCEPT 2>/dev/null",
            f"iptables -D FORWARD -i tailscale0 -o {ap_iface} -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null",
            f"iptables -t nat -D POSTROUTING -s {subnet} -o tailscale0 -j MASQUERADE 2>/dev/null",
        ]
        for cmd in cmds:
            await self._run(cmd)
        log.info("Tailscale iptables routing removed.")

    async def is_installed(self) -> bool:
        rc, _, _ = await self._run("which tailscale")
        return rc == 0
