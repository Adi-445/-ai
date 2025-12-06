from __future__ import annotations
import json
from pathlib import Path
from typing import List

import httpx
from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import agents, memory, models
from .rag import query_rag
from .tools import process_tools, strip_tools
from .db import get_db, init_db, SessionLocal
from .utils import configure_logging

BASE_DIR = Path(__file__).resolve().parent.parent
app = FastAPI(title="Ollama Chat Platform")
configure_logging()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = BASE_DIR / "web"
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

# Initialize DB
init_db(models)


@app.get("/api/new_chat")
def new_chat(db: Session = Depends(get_db)):
    chat = models.Chat(title="New Chat")
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return {"chat_id": chat.id}


@app.get("/api/history/{chat_id}")
def history(chat_id: int, db: Session = Depends(get_db)):
    messages = (
        db.query(models.Message)
        .filter(models.Message.chat_id == chat_id)
        .order_by(models.Message.created_at.asc())
        .all()
    )
    return [
        {"id": msg.id, "role": msg.role, "content": msg.content, "created_at": msg.created_at}
        for msg in messages
    ]


@app.get("/api/memory")
def get_memory(db: Session = Depends(get_db)):
    entries = memory.list_memories(db)
    return [
        {"id": m.id, "text": m.text, "timestamp": m.timestamp}
        for m in entries
    ]


@app.post("/api/memory")
def add_memory(payload: dict, db: Session = Depends(get_db)):
    content = payload.get("content", "")
    entry = memory.write_memory(db, content)
    return {"id": entry.id, "text": entry.text, "timestamp": entry.timestamp}


@app.post("/api/memory/delete")
def delete_memory(payload: dict, db: Session = Depends(get_db)):
    text = payload.get("text", "")
    if text:
        memory.delete_memory(db, text)
    return {"status": "ok"}


@app.post("/api/chat")
def chat(payload: dict, db: Session = Depends(get_db)):
    chat_id = payload.get("chat_id")
    message = payload.get("message", "")
    model = payload.get("model", agents.DEFAULT_MODEL)
    allow_search = bool(payload.get("allow_search", True))
    if not chat_id:
        new = models.Chat(title="New Chat")
        db.add(new)
        db.commit()
        db.refresh(new)
        chat_id = new.id

    history_messages = (
        db.query(models.Message)
        .filter(models.Message.chat_id == chat_id)
        .order_by(models.Message.created_at.asc())
        .all()
    )
    chat_history = [{"role": m.role, "content": m.content} for m in history_messages]

    reply = agents.generate_reply(db, chat_history, message, model=model, allow_search=allow_search)

    for role, content in [("user", message), ("assistant", reply)]:
        msg = models.Message(chat_id=chat_id, role=role, content=content)
        db.add(msg)
    db.commit()
    memory.autosummarize(db)

    return {"chat_id": chat_id, "reply": reply}


async def stream_from_ollama(messages: List[dict], model: str):
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST", agents.OLLAMA_URL, json={"model": model, "messages": messages, "stream": True}
        ) as response:
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                delta = payload.get("message", {}).get("content", "")
                if delta:
                    yield delta


@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    db = SessionLocal()
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            chat_id = data.get("chat_id")
            message = data.get("message", "")
            model = data.get("model", agents.DEFAULT_MODEL)
            allow_search = bool(data.get("allow_search", True))

            if not chat_id:
                chat = models.Chat(title="New Chat")
                db.add(chat)
                db.commit()
                db.refresh(chat)
                chat_id = chat.id

            history_messages = (
                db.query(models.Message)
                .filter(models.Message.chat_id == chat_id)
                .order_by(models.Message.created_at.asc())
                .all()
            )
            chat_history = [{"role": m.role, "content": m.content} for m in history_messages]

            memories = memory.recall_memory(db, message)
            rag_hits = query_rag(message)
            longterm = memory.auto_recall()
            context_blocks = []
            if longterm:
                context_blocks.append("Long-term memory:\n" + "\n".join(longterm))
            if memories:
                context_blocks.append(
                    "Relevant memories:\n" + "\n".join([m.text for m in memories])
                )
            if rag_hits:
                rag_text = "\n---\n".join([f"{name}: {content}" for name, content, _ in rag_hits])
                context_blocks.append(f"Retrieved docs:\n{rag_text}")

            system_msg = {"role": "system", "content": agents.SYSTEM_RULES}
            message_stack = [system_msg]
            if context_blocks:
                message_stack.append({"role": "system", "content": "\n\n".join(context_blocks)})
            message_stack.extend(chat_history)
            message_stack.append({"role": "user", "content": message})

            await websocket.send_json({"type": "status", "message": "stream_start", "chat_id": chat_id})
            accumulated = ""
            async for chunk in stream_from_ollama(message_stack, model=model):
                accumulated += chunk
                await websocket.send_json({"type": "token", "token": chunk})

            processed = process_tools(db, accumulated, allow_search=allow_search)
            clean_processed = strip_tools(processed)

            for role, content in [("user", message), ("assistant", clean_processed)]:
                msg = models.Message(chat_id=chat_id, role=role, content=content)
                db.add(msg)
            db.commit()
            memory.autosummarize(db)

            await websocket.send_json({"type": "final", "content": clean_processed})
            await websocket.send_json({"type": "done", "chat_id": chat_id})
    except WebSocketDisconnect:
        pass
    finally:
        db.close()
        await websocket.close()
