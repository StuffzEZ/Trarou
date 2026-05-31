"""
Shortcuts router.

GET  /api/shortcuts        -- list all shortcuts (public)
POST /api/shortcuts        -- add a shortcut (admin)
DELETE /api/shortcuts/{i}  -- remove a shortcut (admin)
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException

from routers.auth import get_current_admin
from services.shortcuts import ShortcutsService

log = logging.getLogger(__name__)
router = APIRouter()
AdminDep = Annotated[str, Depends(get_current_admin)]
_svc = ShortcutsService()


@router.get("", summary="List all shortcuts")
async def list_shortcuts():
    return {"shortcuts": _svc.get_all()}


@router.post("", summary="Add a shortcut (admin)")
async def add_shortcut(
    admin: AdminDep,
    name: str = Body(..., embed=True),
    url: str = Body(..., embed=True),
    icon: str = Body(default="", embed=True),
):
    entry = _svc.add(name, url, icon)
    log.info(f"Shortcut added by {admin}: {name}")
    return {"status": "added", "shortcut": entry}


@router.delete("/{index}", summary="Remove a shortcut (admin)")
async def remove_shortcut(admin: AdminDep, index: int):
    if not _svc.delete(index):
        raise HTTPException(404, "Shortcut not found")
    log.info(f"Shortcut removed by {admin}: index {index}")
    return {"status": "deleted"}
