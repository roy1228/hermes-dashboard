#!/usr/bin/env python3
"""Hermes API Server — FastAPI backend for the iOS app.

Wraps the hermes CLI to expose REST + WebSocket endpoints.
Authentication via Bearer token (configurable via HERMES_API_KEY env var).

Usage:
    HERMES_API_KEY=mysecret python hermes_api_server.py --port 8000
"""

import asyncio
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))

# ──────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────
HERMES_API_KEY = os.environ.get("HERMES_API_KEY", "")
if not HERMES_API_KEY:
    print(
        "WARNING: HERMES_API_KEY not set. Using default key 'hermes'.", file=sys.stderr
    )
    HERMES_API_KEY = "hermes"

security = HTTPBearer(auto_error=False)


def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    if not credentials or credentials.credentials != HERMES_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ──────────────────────────────────────────────
# Shell helpers
# ──────────────────────────────────────────────
async def _shell_async(cmd: str, timeout: int | None = None) -> str:
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={
                **os.environ,
                "HERMES_HOME": str(HERMES_HOME),
                "HERMES_YOLO_MODE": "1",
            },
        )
        if timeout is None:
            stdout, _ = await proc.communicate()
        else:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return (stdout.decode() if stdout else "").strip()
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return "(timeout)"
    except Exception as e:
        return f"(error: {e})"


async def _shell_async_stream(cmd: str):
    """Async generator that yields stdout chunks as they arrive."""
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={
                **os.environ,
                "HERMES_HOME": str(HERMES_HOME),
                "HERMES_YOLO_MODE": "1",
            },
        )
        if proc.stdout is None:
            return
        while True:
            chunk = await proc.stdout.read(512)
            if not chunk:
                break
            yield chunk.decode()
        await proc.wait()
    except Exception:
        return


# ──────────────────────────────────────────────
# Pydantic models
# ──────────────────────────────────────────────
class SessionInfo(BaseModel):
    id: str
    title: str
    ago: str
    group: str


class SessionDetail(BaseModel):
    id: str
    model: str
    message_count: int
    messages: list[dict]


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    response: str


# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────
app = FastAPI(title="Hermes API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _parse_ago_to_hours(ago: str | None) -> int | None:
    if not ago:
        return None
    ago = ago.strip().lower()
    if ago == "just now":
        return 0
    m = re.match(r"^(\d+)\s*([mhd])\s*(ago)?$", ago)
    if not m:
        return None
    value = int(m.group(1))
    unit = m.group(2)
    if unit == "m":
        return 0
    elif unit == "h":
        return value
    elif unit == "d":
        return value * 24


GROUPS = [
    ("今天（24h 内）", lambda h: h is not None and h < 24, 0),
    ("3 天内", lambda h: h is not None and 24 <= h < 72, 1),
    ("3-7 天", lambda h: h is not None and 72 <= h < 168, 2),
    ("7 天-1 个月", lambda h: h is not None and 168 <= h < 720, 3),
    ("1 个月以上", lambda h: h is not None and h >= 720, 4),
    ("未知时间", lambda h: True, 5),
]


def _get_group_name(hours: int | None) -> str:
    for name, predicate, _ in GROUPS:
        if predicate(hours):
            return name
    return "未知时间"


def _parse_chat_output(raw: str) -> tuple[str | None, str]:
    if not raw:
        return (None, "")
    lines = raw.split("\n")
    session_id = None
    response_start = 0
    for i, line in enumerate(lines):
        if line.startswith("session_id:"):
            session_id = line.split(":", 1)[1].strip()
            response_start = i + 1
            break
    if response_start < len(lines) and not lines[response_start].strip():
        response_start += 1
    response = "\n".join(lines[response_start:]).strip()
    return (session_id, response)


# ──────────────────────────────────────────────
# Session endpoints
# ──────────────────────────────────────────────
@app.get("/api/sessions", response_model=list[SessionInfo])
async def list_sessions(_=Depends(verify_token)):
    raw = await _shell_async("hermes sessions list --limit 200", timeout=20)
    sessions = []
    for line in raw.strip().split("\n"):
        if not line.strip() or line.startswith("Title") or line.startswith("─"):
            continue
        if "cron_" in line:
            continue
        m = re.search(r"(\d{8}_\d{6}_[0-9a-f]+|[0-9a-f]{12,})\s*$", line)
        if not m:
            continue
        sid = m.group(1)
        before = line[: m.start()].rstrip()
        m2 = re.search(r"(\d+[mhd]\s+ago|just\s+now)\s*$", before)
        ago = m2.group(1) if m2 else ""
        title = line[:32].strip()
        title = re.sub(r"\s{2,}", " ", title)
        preview_start = 32
        preview_end = before.rfind(ago) - 1 if ago and m2 else len(before)
        preview = (
            line[preview_start : max(preview_end, preview_start)].strip()
            if preview_end > preview_start
            else ""
        )
        display_name = (
            preview[:40] if title in ("—", "None", "") or len(title) < 2 else title
        )
        hours = _parse_ago_to_hours(ago)
        group = _get_group_name(hours)
        sessions.append(
            {
                "id": sid,
                "title": display_name,
                "ago": ago,
                "group": group,
            }
        )
    return sessions


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str, _=Depends(verify_token)):
    raw = await _shell_async(
        f"hermes sessions export --session-id {session_id} -", timeout=25
    )
    if not raw or raw.startswith("(timeout)") or raw.startswith("(error:"):
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to parse session data")

    msgs = data.get("messages", [])
    model = data.get("model", "?")
    clean_messages = []
    for m in msgs:
        role = m.get("role", "")
        content = str(m.get("content", "")).strip()
        if role == "assistant" and not content and not m.get("tool_calls"):
            continue
        if role == "tool" and not content:
            continue
        clean_messages.append(
            {
                "role": role,
                "content": content,
                "name": m.get("name") if role == "tool" else None,
            }
        )
    return {
        "id": session_id,
        "model": model,
        "message_count": len(clean_messages),
        "messages": clean_messages,
    }


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, _=Depends(verify_token)):
    result = await _shell_async(f"hermes sessions delete {session_id}", timeout=15)
    return {"deleted": session_id, "result": result}


# ──────────────────────────────────────────────
# Chat endpoints (REST fallback)
# ──────────────────────────────────────────────
@app.post("/api/chat/new")
async def chat_new(request: ChatRequest, _=Depends(verify_token)):
    """Start a new chat session. Returns session_id + response."""
    safe_msg = shlex.quote(request.message)
    cmd = f"hermes chat -q {safe_msg} -Q 2>&1"
    output = await _shell_async(cmd, timeout=120)
    session_id, response = _parse_chat_output(output)
    if not session_id:
        raise HTTPException(status_code=500, detail=f"Chat failed: {output[:200]}")
    return {"session_id": session_id, "response": response}


@app.post("/api/chat/resume")
async def chat_resume(request: ChatRequest, _=Depends(verify_token)):
    """Resume an existing session. Returns response."""
    if not request.session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    safe_sid = shlex.quote(request.session_id)
    safe_msg = shlex.quote(request.message)
    cmd = f"hermes chat -r {safe_sid} -q {safe_msg} -Q 2>&1"
    output = await _shell_async(cmd, timeout=120)
    session_id, response = _parse_chat_output(output)
    return {"session_id": session_id or request.session_id, "response": response}


# ──────────────────────────────────────────────
# WebSocket streaming chat
# ──────────────────────────────────────────────
@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            message = payload.get("message", "").strip()
            session_id = payload.get("session_id")
            if not message:
                await websocket.send_json({"type": "error", "message": "Empty message"})
                continue

            # Build command
            if session_id:
                safe_sid = shlex.quote(session_id)
                safe_msg = shlex.quote(message)
                cmd = f"hermes chat -r {safe_sid} -q {safe_msg} -Q 2>&1"
            else:
                safe_msg = shlex.quote(message)
                cmd = f"hermes chat -q {safe_msg} -Q 2>&1"

            # Send session_id if resumed
            if session_id:
                await websocket.send_json(
                    {"type": "session_id", "session_id": session_id}
                )

            await websocket.send_json({"type": "start"})

            full_output = ""
            async for chunk in _shell_async_stream(cmd):
                full_output += chunk
                # Send chunk to client
                await websocket.send_json({"type": "chunk", "text": chunk})

            # Parse final output
            sid, response = _parse_chat_output(full_output)
            await websocket.send_json(
                {
                    "type": "done",
                    "session_id": sid or session_id,
                    "response": response,
                }
            )
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.send_json({"type": "error", "message": "Server error"})
        except Exception:
            pass


# ──────────────────────────────────────────────
# Health check
# ──────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok", "hermes_home": str(HERMES_HOME)}


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Hermes API Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
