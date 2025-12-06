import asyncio
import datetime as dt
import json
import os
import shutil
import sqlite3
import subprocess
import threading
from pathlib import Path
from typing import List, Optional

import httpx
import numpy as np
from fastapi import BackgroundTasks, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).parent
MEMORY_DIR = BASE_DIR / "memory"
DB_PATH = MEMORY_DIR / "memory.db"
WEB_DIR = BASE_DIR / "web"
AGENT_DIR = BASE_DIR / "agent"
MODEL_NAME = "smollm2x"
SERVER_PORT = 7860

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


class ChatRequest(BaseModel):
    chat_id: int
    message: str


class MemoryAddRequest(BaseModel):
    content: str
    source: Optional[str] = "user"


class SearchRequest(BaseModel):
    query: str


class RecallQuery(BaseModel):
    query: str


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY(chat_id) REFERENCES chats(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                source TEXT,
                timestamp TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS search_cache (
                query TEXT PRIMARY KEY,
                result TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )
        conn.commit()


model = SentenceTransformer("all-MiniLM-L6-v2")
embeddings_store = []
message_since_reindex = 0
store_lock = threading.Lock()


def backup_database_daily():
    def _run():
        while True:
            date_str = dt.datetime.utcnow().strftime("%Y-%m-%d")
            backup_path = MEMORY_DIR / f"memory_backup_{date_str}.db"
            try:
                shutil.copy(DB_PATH, backup_path)
            except Exception:
                pass
            finally:
                # sleep for 24 hours
                time_to_sleep = 24 * 60 * 60
                threading.Event().wait(time_to_sleep)

    threading.Thread(target=_run, daemon=True).start()


def cleanup_search_cache():
    with get_db_connection() as conn:
        cutoff = (dt.datetime.utcnow() - dt.timedelta(days=30)).isoformat()
        cur = conn.cursor()
        cur.execute("DELETE FROM search_cache WHERE timestamp < ?", (cutoff,))
        conn.commit()


def embed_text(text: str) -> np.ndarray:
    return model.encode([text], convert_to_numpy=True)[0]


def refresh_embeddings():
    global embeddings_store, message_since_reindex
    with store_lock:
        combined = []
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT content, role FROM messages")
            for row in cur.fetchall():
                combined.append((f"{row['role']}: {row['content']}", "chat"))
            cur.execute("SELECT content, source FROM memory")
            for row in cur.fetchall():
                combined.append((row[0], row[1] or "memory"))
        embeddings_store = [
            {
                "text": text,
                "source": source,
                "embedding": embed_text(text),
            }
            for text, source in combined
        ]
        message_since_reindex = 0


async def recall_context(query: str, top_k: int = 3):
    if not embeddings_store:
        return []
    query_vec = embed_text(query)
    scores = []
    for idx, item in enumerate(embeddings_store):
        vec = item["embedding"]
        similarity = float(np.dot(query_vec, vec) / (np.linalg.norm(query_vec) * np.linalg.norm(vec) + 1e-10))
        scores.append((similarity, idx))
    top_items = sorted(scores, reverse=True)[:top_k]
    return [embeddings_store[i] for _, i in top_items]


async def get_chat_history(chat_id: int, limit: int = 5):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT role, content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        )
        rows = cur.fetchall()
    history = list(reversed(rows))
    return [{"role": r[0], "content": r[1]} for r in history]


def store_message(chat_id: int, role: str, content: str):
    global message_since_reindex
    timestamp = dt.datetime.utcnow().isoformat()
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO messages(chat_id, role, content, timestamp) VALUES (?,?,?,?)",
            (chat_id, role, content, timestamp),
        )
        conn.commit()
    message_since_reindex += 1
    if message_since_reindex >= 10:
        refresh_embeddings()


def detect_tags(message: str):
    tags = {"search": [], "recall": []}
    if "<web.search>" in message:
        parts = message.split("<web.search>")
        for part in parts[1:]:
            query = part.split("</web.search>")[0] if "</web.search>" in part else part
            tags["search"].append(query.strip())
    if "<recall>" in message:
        parts = message.split("<recall>")
        for part in parts[1:]:
            query = part.split("</recall>")[0] if "</recall>" in part else part
            tags["recall"].append(query.strip())
    return tags


async def run_search(query: str):
    # check cache first
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT result FROM search_cache WHERE query=?", (query,))
        row = cur.fetchone()
        if row:
            return row[0]

    script_path = AGENT_DIR / "search.sh"
    process = await asyncio.create_subprocess_exec(
        "bash",
        str(script_path),
        query,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if stderr:
        print("Search error:", stderr.decode())
    result_text = stdout.decode().strip() or "No results"
    timestamp = dt.datetime.utcnow().isoformat()
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO search_cache(query, result, timestamp) VALUES (?,?,?)",
            (query, result_text, timestamp),
        )
        conn.commit()
    print("[RAG + WebSearch + LocalRecall] web.search triggered")
    return result_text


async def query_local_recall(query: str):
    results = await recall_context(query, top_k=3)
    print("[RAG + WebSearch + LocalRecall] recall triggered")
    return "\n".join([f"- {item['text']} (source: {item['source']})" for item in results])


async def build_prompt(chat_id: int, user_message: str, recalls: List[str]):
    history = await get_chat_history(chat_id, limit=5)
    context_lines = []
    if recalls:
        context_lines.append("Relevant memories:")
        context_lines.extend(recalls)
    rag_memories = await recall_context(user_message)
    if rag_memories:
        context_lines.append("Related context:")
        for item in rag_memories:
            context_lines.append(f"- {item['text']} (source: {item['source']})")
        print("[RAG + WebSearch + LocalRecall] RAG context used")
    system_prompt = "You are a helpful assistant that uses provided context and memory. "
    if context_lines:
        system_prompt += "\n\n" + "\n".join(context_lines)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return messages


async def stream_ollama(messages: List[dict]):
    url = "http://localhost:11434/api/chat"
    payload = {"model": MODEL_NAME, "messages": messages, "stream": True}
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", url, json=payload) as response:
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("done"):
                    break
                yield data.get("message", {}).get("content", "")


async def handle_chat(chat_id: int, user_message: str):
    tags = detect_tags(user_message)
    recalls = []
    for query in tags["recall"]:
        recalls.append(await query_local_recall(query))
    if tags["search"]:
        search_results = []
        for query in tags["search"]:
            search_results.append(await run_search(query))
        user_message += "\n\nSearch Results:\n" + "\n".join(search_results)
    prompt_messages = await build_prompt(chat_id, user_message, recalls)
    response_content = ""
    async for chunk in stream_ollama(prompt_messages):
        response_content += chunk
        yield chunk
    store_message(chat_id, "assistant", response_content)


@app.on_event("startup")
def on_startup():
    init_db()
    refresh_embeddings()
    cleanup_search_cache()
    backup_database_daily()


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/history/{chat_id}")
async def history(chat_id: int):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT role, content, timestamp FROM messages WHERE chat_id=? ORDER BY id",
            (chat_id,),
        )
        rows = cur.fetchall()
    return {"chat_id": chat_id, "messages": [dict(row) for row in rows]}


@app.post("/new_chat")
async def new_chat():
    timestamp = dt.datetime.utcnow()
    title = f"Chat {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO chats(title, timestamp) VALUES (?,?)",
            (title, timestamp.isoformat()),
        )
        chat_id = cur.lastrowid
        conn.commit()
    refresh_embeddings()
    return {"chat_id": chat_id, "title": title}


@app.get("/list_chats")
async def list_chats():
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, title, timestamp FROM chats ORDER BY id DESC")
        rows = cur.fetchall()
    return {"chats": [dict(row) for row in rows]}


@app.post("/memory/add")
async def add_memory(payload: MemoryAddRequest):
    timestamp = dt.datetime.utcnow().isoformat()
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO memory(content, source, timestamp) VALUES (?,?,?)",
            (payload.content, payload.source, timestamp),
        )
        conn.commit()
    refresh_embeddings()
    return {"status": "ok", "timestamp": timestamp}


@app.get("/memory/all")
async def list_memory():
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, content, source, timestamp FROM memory ORDER BY id DESC")
        rows = cur.fetchall()
    return {"memory": [dict(row) for row in rows]}


@app.post("/agent/search")
async def agent_search(payload: SearchRequest):
    result = await run_search(payload.query)
    return {"result": result}


@app.post("/recall/query")
async def recall_query(payload: RecallQuery):
    recall_text = await query_local_recall(payload.query)
    return {"result": recall_text}


@app.post("/chat")
async def chat_endpoint(payload: ChatRequest):
    store_message(payload.chat_id, "user", payload.message)
    refresh_needed = False
    async def event_generator():
        async for chunk in handle_chat(payload.chat_id, payload.message):
            yield chunk
    content = ""
    async for chunk in event_generator():
        content += chunk
    # Also return full content
    emotion = None
    for tag in ["happy", "sad", "neutral", "angry"]:
        if f"emotion:{tag}" in content:
            emotion = tag
            break
    return {"response": content, "emotion": emotion}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                chat_id = int(payload.get("chat_id"))
                message = payload.get("message", "")
            except Exception:
                await websocket.send_text(json.dumps({"error": "Invalid payload"}))
                continue
            store_message(chat_id, "user", message)
            collected = ""
            async for chunk in handle_chat(chat_id, message):
                collected += chunk
                await websocket.send_text(json.dumps({"chunk": chunk}))
            emotion = None
            for tag in ["happy", "sad", "neutral", "angry"]:
                if f"emotion:{tag}" in collected:
                    emotion = tag
                    break
            await websocket.send_text(json.dumps({"done": True, "full": collected, "emotion": emotion}))
    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)
