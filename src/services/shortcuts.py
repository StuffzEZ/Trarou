"""
ShortcutsService -- manages user-defined app shortcuts.

Stored in /etc/trarou/shortcuts.json so all users see the same shortcuts.
Only admins can add/remove shortcuts.
"""

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

SHORTCUTS_FILE = Path("/etc/trarou/shortcuts.json")


class ShortcutsService:

    def _load(self) -> list[dict]:
        if SHORTCUTS_FILE.exists():
            try:
                return json.loads(SHORTCUTS_FILE.read_text())
            except Exception:
                return []
        return []

    def _save(self, shortcuts: list[dict]):
        SHORTCUTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SHORTCUTS_FILE.write_text(json.dumps(shortcuts, indent=2))

    def get_all(self) -> list[dict]:
        return self._load()

    def add(self, name: str, url: str, icon: str = "") -> dict:
        shortcuts = self._load()
        entry = {"name": name, "url": url, "icon": icon or "\U0001F4F1"}
        shortcuts.append(entry)
        self._save(shortcuts)
        return entry

    def delete(self, index: int) -> bool:
        shortcuts = self._load()
        if 0 <= index < len(shortcuts):
            shortcuts.pop(index)
            self._save(shortcuts)
            return True
        return False
