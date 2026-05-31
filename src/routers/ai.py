"""
AI router.

GET  /api/ai/status              -- backend availability + recommendations
POST /api/ai/chat                -- SSE streaming
GET  /api/ai/models              -- list installed models
POST /api/ai/pull-model          -- pull a model (admin)
DELETE /api/ai/delete-model/{m}  -- remove a model (admin)
POST /api/ai/auto-setup          -- auto-pull recommended model
GET  /api/ai/recommend           -- get model recommendations for this hardware
GET  /api/ai/knowledge
POST /api/ai/knowledge           -- admin
DELETE /api/ai/knowledge/{id}    -- admin
GET  /api/ai/system-prompt       -- admin
POST /api/ai/system-prompt       -- admin
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse

from routers.auth import get_current_admin
from services.ai import AIService

log = logging.getLogger(__name__)
router = APIRouter()
AdminDep = Annotated[str, Depends(get_current_admin)]
_ai = AIService()

_SYSTEM_PROMPT_FILE = Path("/etc/trarou/ai_system_prompt.txt")


def _get_custom_prompt() -> str:
    if _SYSTEM_PROMPT_FILE.exists():
        return _SYSTEM_PROMPT_FILE.read_text().strip()
    return ""


def _set_custom_prompt(text: str):
    _SYSTEM_PROMPT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SYSTEM_PROMPT_FILE.write_text(text)


@router.get("/status", summary="AI backend status")
async def ai_status():
    return await _ai.status()


@router.get("/recommend", summary="Get model recommendations for this hardware")
async def ai_recommend():
    return _ai.recommend_model()


@router.post("/auto-setup", summary="Auto-pull the best model for this hardware")
async def ai_auto_setup():
    return await _ai.auto_setup()


@router.post("/chat", summary="Chat with the Trarou AI (SSE stream)")
async def ai_chat(
    messages: list[dict] = Body(...),
    model: Optional[str] = Body(default=None),
):
    custom_suffix = _get_custom_prompt()

    async def event_stream():
        try:
            async for chunk in _ai.chat_stream(messages, model=model, custom_system_suffix=custom_suffix):
                payload = json.dumps({"chunk": chunk})
                yield f"data: {payload}\n\n"
                await asyncio.sleep(0)
        except Exception as e:
            log.error(f"AI stream error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/models", summary="List installed models")
async def list_models():
    if not await _ai.ollama_available():
        return {"models": [], "ollama_available": False}
    models = await _ai.ollama_models()
    return {"models": models, "ollama_available": True}


@router.post("/pull-model", summary="Pull an Ollama model (admin)")
async def pull_model(admin: AdminDep, model: str = Body(..., embed=True)):
    if not await _ai.ollama_available():
        raise HTTPException(400, "Ollama is not available.")

    async def progress_stream():
        async for line in _ai.ollama_pull(model):
            yield f"data: {line}\n\n"
            await asyncio.sleep(0)
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(progress_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.delete("/delete-model/{model:path}", summary="Remove an installed model (admin)")
async def delete_model(admin: AdminDep, model: str):
    if not await _ai.ollama_available():
        raise HTTPException(400, "Ollama is not available.")
    ok = await _ai.ollama_delete(model)
    if not ok:
        raise HTTPException(500, "Failed to delete model")
    return {"status": "deleted", "model": model}


@router.get("/knowledge", summary="List knowledge base entries")
async def get_knowledge():
    return {"entries": _ai.get_knowledge()}


@router.post("/knowledge", summary="Add a knowledge base entry (admin)")
async def add_knowledge(
    admin: AdminDep,
    title: str = Body(..., embed=True),
    content: str = Body(..., embed=True),
):
    entry = _ai.add_knowledge(title, content)
    return {"status": "added", "entry": entry}


@router.delete("/knowledge/{entry_id}", summary="Delete a knowledge base entry (admin)")
async def delete_knowledge(admin: AdminDep, entry_id: str):
    if not _ai.delete_knowledge(entry_id):
        raise HTTPException(404, "Entry not found")
    return {"status": "deleted"}


@router.get("/system-prompt", summary="Get custom system prompt suffix")
async def get_system_prompt(admin: AdminDep):
    return {"prompt": _get_custom_prompt()}


@router.post("/system-prompt", summary="Set custom system prompt suffix (admin)")
async def set_system_prompt(admin: AdminDep, prompt: str = Body(..., embed=True)):
    _set_custom_prompt(prompt)
    return {"status": "updated"}
