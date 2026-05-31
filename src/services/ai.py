"""
AIService -- local AI for Trarou, optimized for Raspberry Pi.

Models are selected based on available RAM:
  - 1GB RAM  -> smollm2:135m (ultra-fast, basic)
  - 2GB RAM  -> tinyllama (fast, decent quality)
  - 4GB RAM  -> gemma2:2b (Google, good quality)
  - 8GB RAM  -> gemma2:2b or phi3.5:mini (best quality)

All models run fully locally via Ollama. No cloud APIs.

Browser AI: Gemini Nano via Chrome's window.ai (on-device, no server needed).
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import AsyncIterator, Optional

log = logging.getLogger(__name__)

KNOWLEDGE_FILE = Path("/etc/trarou/ai_knowledge.json")

# Curated models optimized for edge devices, ordered by quality
# Each entry: (name, ram_needed_mb, description, quality)
RECOMMENDED_MODELS = [
    ("smollm2:135m",   512,  "Ultra-fast, basic responses",          "basic"),
    ("tinyllama:1.1b", 1024, "Fast, good for simple tasks",          "fast"),
    ("gemma2:2b",      2048, "Google model, best quality for 2-4GB", "good"),
    ("phi3.5:mini",    3072, "Microsoft, excellent reasoning",       "best"),
    ("gemma2:9b",      6144, "Large Google model, needs 8GB+",       "premium"),
]

BUILTIN_KNOWLEDGE = """
You are the Trarou AI assistant, built into the Trarou travel router.

ABOUT TRAROU:
Trarou is an open-source travel router that turns a Raspberry Pi into a smart Wi-Fi hotspot.
It creates its own Wi-Fi network (AP) and connects upstream to hotels/airports/cafes via a second Wi-Fi adapter.

ARCHITECTURE:
- Backend: FastAPI on port 8000
- Frontend: Static HTML/JS/CSS on port 3000
- AP interface: wlan0 (or configured via AP_INTERFACE)
- Client interface: wlan1 (or configured via CLIENT_INTERFACE)
- Config file: /etc/trarou/trarou.env
- Logs: /var/log/trarou/trarou.log
- Media storage: ~/trarou-media

KEY FEATURES:
- Captive portal that lets devices join the AP automatically
- Media server for sharing files over the local network
- VNC remote desktop for accessing captive portal login pages
- Network scanning and upstream Wi-Fi management
- Tailscale VPN integration (share one Tailscale node with all AP clients)
- Local AI assistant (you!)

COMMON TROUBLESHOOTING:
- AP not starting: Check 'systemctl status trarou', ensure wlan0 supports AP mode with 'iw list'
- Can't connect upstream: Check 'nmcli dev status', try 'systemctl restart NetworkManager'
- Media not showing: Check ~/trarou-media exists and has files
- Backend not responding: Check 'journalctl -u trarou -n 50'
- Tailscale issues: Run 'tailscale status' in terminal
- VNC issues: Ensure x11vnc/tigervnc is installed, check port 5900

HELPFUL COMMANDS:
- Restart backend: sudo systemctl restart trarou
- Check logs: sudo journalctl -u trarou -f
- Check AP status: sudo hostapd_cli status
- Network interfaces: ip addr show
- Connected clients: arp -i wlan0
"""


class AIService:

    def _get_ram_mb(self) -> int:
        """Get total system RAM in MB."""
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        return int(line.split()[1]) // 1024
        except Exception:
            pass
        return 2048  # default assumption

    def _load_knowledge(self) -> list[dict]:
        if KNOWLEDGE_FILE.exists():
            try:
                return json.loads(KNOWLEDGE_FILE.read_text())
            except Exception:
                return []
        return []

    def _save_knowledge(self, entries: list[dict]):
        KNOWLEDGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        KNOWLEDGE_FILE.write_text(json.dumps(entries, indent=2))

    def get_knowledge(self) -> list[dict]:
        return self._load_knowledge()

    def add_knowledge(self, title: str, content: str) -> dict:
        entries = self._load_knowledge()
        entry = {"id": str(int(time.time() * 1000)), "title": title, "content": content}
        entries.append(entry)
        self._save_knowledge(entries)
        return entry

    def delete_knowledge(self, entry_id: str) -> bool:
        entries = self._load_knowledge()
        new_entries = [e for e in entries if e.get("id") != entry_id]
        if len(new_entries) == len(entries):
            return False
        self._save_knowledge(new_entries)
        return True

    def _build_system_prompt(self, custom_suffix: str = "") -> str:
        user_knowledge = self._load_knowledge()
        prompt = BUILTIN_KNOWLEDGE
        if user_knowledge:
            prompt += "\n\nUSER-ADDED KNOWLEDGE:\n"
            for entry in user_knowledge:
                prompt += f"\n## {entry['title']}\n{entry['content']}\n"
        if custom_suffix:
            prompt += f"\n\n{custom_suffix}"
        return prompt

    def recommend_model(self) -> dict:
        """Recommend the best model based on available RAM."""
        ram_mb = self._get_ram_mb()
        # Pick the largest model that fits in available RAM (with headroom)
        usable = ram_mb - 512  # leave 512MB for OS
        best = RECOMMENDED_MODELS[0]
        for name, needed, desc, quality in RECOMMENDED_MODELS:
            if needed <= usable:
                best = (name, needed, desc, quality)
        return {
            "ram_mb": ram_mb,
            "recommended": best[0],
            "description": best[2],
            "quality": best[3],
            "all_models": [
                {"name": m[0], "ram_needed_mb": m[1], "description": m[2], "quality": m[3], "fits": m[1] <= usable}
                for m in RECOMMENDED_MODELS
            ],
        }

    # -- Ollama ---------------------------------------------------------------

    async def ollama_available(self) -> bool:
        try:
            loop = asyncio.get_event_loop()
            def check():
                try:
                    import urllib.request
                    with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as r:
                        return r.status == 200
                except Exception:
                    return False
            return await loop.run_in_executor(None, check)
        except Exception:
            return False

    async def ollama_models(self) -> list[str]:
        try:
            loop = asyncio.get_event_loop()
            def fetch():
                import urllib.request
                with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
                    return json.loads(r.read())
            data = await loop.run_in_executor(None, fetch)
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    async def ollama_stream(self, messages: list[dict], model: str, system: str) -> AsyncIterator[str]:
        import urllib.request
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "system", "content": system}] + messages,
            "stream": True,
            "options": {
                "num_predict": 512,
                "temperature": 0.7,
                "top_p": 0.9,
                "num_ctx": 2048,
            },
        }).encode()

        def do_stream():
            req = urllib.request.Request(
                "http://localhost:11434/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                for line in resp:
                    line = line.strip()
                    if line:
                        try:
                            obj = json.loads(line)
                            content = obj.get("message", {}).get("content", "")
                            if content:
                                yield content
                        except Exception:
                            pass

        # Run the generator in an executor and yield chunks
        loop = asyncio.get_event_loop()
        gen = do_stream()
        while True:
            try:
                chunk = await loop.run_in_executor(None, lambda: next(gen, None))
                if chunk is None:
                    break
                yield chunk
            except StopIteration:
                break
            except Exception:
                break

    async def ollama_pull(self, model: str) -> AsyncIterator[str]:
        import urllib.request
        payload = json.dumps({"name": model}).encode()
        loop = asyncio.get_event_loop()

        def do_pull():
            req = urllib.request.Request(
                "http://localhost:11434/api/pull",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            lines = []
            with urllib.request.urlopen(req, timeout=600) as resp:
                for line in resp:
                    line = line.strip()
                    if line:
                        lines.append(line.decode())
            return lines

        lines = await loop.run_in_executor(None, do_pull)
        for line in lines:
            yield line

    async def ollama_delete(self, model: str) -> bool:
        import urllib.request
        payload = json.dumps({"name": model}).encode()
        try:
            loop = asyncio.get_event_loop()
            def do_delete():
                req = urllib.request.Request(
                    "http://localhost:11434/api/delete",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="DELETE",
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    return r.status == 200
            return await loop.run_in_executor(None, do_delete)
        except Exception:
            return False

    # -- Auto-setup -----------------------------------------------------------

    _pull_task: asyncio.Task | None = None

    async def auto_setup(self) -> dict:
        """Auto-pull the recommended model if no models are installed."""
        if not await self.ollama_available():
            return {"status": "ollama_not_available"}

        models = await self.ollama_models()
        if models:
            return {"status": "already_configured", "models": models}

        rec = self.recommend_model()
        model = rec["recommended"]
        log.info(f"Auto-pulling recommended model: {model}")

        # Pull in background and store reference to prevent GC
        self._pull_task = asyncio.create_task(self._background_pull(model))
        return {"status": "pulling", "model": model, "description": rec["description"]}

    async def _background_pull(self, model: str):
        """Pull model in background, log progress."""
        try:
            async for line in self.ollama_pull(model):
                pass
            log.info(f"Model {model} pulled successfully")
        except Exception as e:
            log.error(f"Failed to pull {model}: {e}")

    # -- Unified chat ----------------------------------------------------------

    async def chat_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        custom_system_suffix: str = "",
    ) -> AsyncIterator[str]:
        system = self._build_system_prompt(custom_system_suffix)

        if await self.ollama_available():
            models = await self.ollama_models()
            if not models:
                # No models installed -- auto-pull recommended
                rec = self.recommend_model()
                yield f"No models installed. Auto-downloading {rec['recommended']} ({rec['description']})...\n\n"
                async for line in self.ollama_pull(rec["recommended"]):
                    pass
                models = await self.ollama_models()

            chosen = model if (model and model in models) else (models[0] if models else None)
            if chosen:
                async for chunk in self.ollama_stream(messages, chosen, system):
                    yield chunk
                return

        yield "Ollama is not running. Install it: curl -fsSL https://ollama.com/install.sh | sh"

    async def status(self) -> dict:
        ollama_ok = await self.ollama_available()
        models = await self.ollama_models() if ollama_ok else []
        rec = self.recommend_model()
        return {
            "ollama": {"available": ollama_ok, "models": models},
            "browser_ai": {"available": True, "note": "Gemini Nano via Chrome window.ai"},
            "active_backend": "ollama" if ollama_ok else "browser",
            "recommendation": rec,
        }
