"""
Media router.

GET  /api/media/tree          — full recursive JSON tree of trarou-media
GET  /api/media/list          — flat file list (optional ?folder= filter)
POST /api/media/upload        — admin: upload one or more files
DELETE /api/media/file        — admin: delete a file
POST /api/media/folder        — admin: create a sub-folder
DELETE /api/media/folder      — admin: delete an empty folder
"""

import logging
import mimetypes
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from config import settings
from models.schemas import MediaFile, MediaFolder, MediaTree
from routers.auth import get_current_admin

log = logging.getLogger(__name__)
router = APIRouter()

AdminDep = Annotated[str, Depends(get_current_admin)]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _media_dir() -> Path:
    return settings.MEDIA_DIR


def _rel(path: Path) -> str:
    return str(path.relative_to(_media_dir()))


def _file_info(path: Path) -> MediaFile:
    rel = _rel(path)
    mime, _ = mimetypes.guess_type(path.name)
    stat = path.stat()
    return MediaFile(
        name=path.name,
        path=rel,
        url=f"/media-files/{rel}",
        size_bytes=stat.st_size,
        mime_type=mime or "application/octet-stream",
        modified_at=datetime.fromtimestamp(stat.st_mtime),
    )


def _folder_info(path: Path) -> MediaFolder:
    children = list(path.iterdir())
    return MediaFolder(
        name=path.name,
        path=_rel(path),
        children_count=len(children),
    )


def _safe_path(rel_path: str) -> Path:
    """Resolve a relative path safely within the media dir."""
    base = _media_dir().resolve()
    target = (base / rel_path).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    return target


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/tree", response_model=MediaTree, summary="Full recursive media tree")
async def get_media_tree():
    """
    Returns the complete folder/file tree of the trarou-media directory.
    Safe for unauthenticated use — this is the public browsing endpoint.
    """
    base = _media_dir()
    base.mkdir(parents=True, exist_ok=True)

    folders: list[MediaFolder] = []
    files: list[MediaFile] = []
    total_size = 0

    for root, dirs, filenames in os.walk(base):
        root_path = Path(root)
        dirs.sort()

        # Skip root itself from folder list
        if root_path != base:
            folders.append(_folder_info(root_path))

        for fname in sorted(filenames):
            fpath = root_path / fname
            try:
                fi = _file_info(fpath)
                files.append(fi)
                total_size += fi.size_bytes
            except Exception as e:
                log.warning(f"Skipping {fpath}: {e}")

    return MediaTree(
        folders=folders,
        files=files,
        total_files=len(files),
        total_size_bytes=total_size,
    )


@router.get("/list", summary="Flat file list (optional folder filter)")
async def list_files(folder: Optional[str] = Query(default=None)):
    """
    Returns files in a specific sub-folder (or root if no ?folder= given).
    """
    base = _media_dir()
    target = _safe_path(folder) if folder else base
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    files = [_file_info(p) for p in sorted(target.iterdir()) if p.is_file()]
    subdirs = [_folder_info(p) for p in sorted(target.iterdir()) if p.is_dir()]
    return {"path": folder or "/", "folders": subdirs, "files": files}


@router.post("/upload", summary="Admin: upload files to a folder")
async def upload_files(
    admin: AdminDep,
    files: list[UploadFile] = File(...),
    folder: str = Form(default=""),
):
    """
    Uploads one or more files into the specified sub-folder (default: root).
    Max size governed by MAX_UPLOAD_SIZE_MB setting.
    """
    target_dir = _safe_path(folder) if folder else _media_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    uploaded = []

    for uf in files:
        if not uf.filename:
            continue
        dest = target_dir / Path(uf.filename).name  # strip any directory parts
        size = 0
        with open(dest, "wb") as f:
            while chunk := await uf.read(1024 * 1024):  # 1 MB chunks
                size += len(chunk)
                if size > max_bytes:
                    f.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(413, f"File {uf.filename} exceeds size limit")
                f.write(chunk)
        log.info(f"Admin uploaded: {dest} ({size} bytes)")
        uploaded.append({"name": uf.filename, "size_bytes": size})

    return {"uploaded": uploaded}


@router.delete("/file", summary="Admin: delete a file")
async def delete_file(admin: AdminDep, path: str = Query(...)):
    target = _safe_path(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found")
    target.unlink()
    log.info(f"Admin deleted file: {target}")
    return {"deleted": path}


@router.post("/folder", summary="Admin: create a folder")
async def create_folder(admin: AdminDep, path: str = Form(...)):
    target = _safe_path(path)
    target.mkdir(parents=True, exist_ok=True)
    log.info(f"Admin created folder: {target}")
    return {"created": path}


@router.delete("/folder", summary="Admin: delete an empty folder")
async def delete_folder(admin: AdminDep, path: str = Query(...)):
    if not path or path in (".", "/", ""):
        raise HTTPException(400, "Cannot delete root media folder")
    target = _safe_path(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "Folder not found")
    try:
        shutil.rmtree(target)
    except Exception as e:
        raise HTTPException(500, f"Could not delete folder: {e}")
    log.info(f"Admin deleted folder: {target}")
    return {"deleted": path}
