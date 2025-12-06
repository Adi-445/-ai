import logging
from typing import List, Dict, Any

import httpx
from sqlalchemy.orm import Session

from . import memory
from .rag import query_rag
from .tools import process_tools

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "smollm2x"
SYSTEM_RULES = (
    "You are a helpful local assistant. Do not claim emotions or self-awareness. "
    "Use external web search only when users ask about current events or missing knowledge."
)


def _ollama_chat(messages: List[Dict[str, str]], model: str = DEFAULT_MODEL) -> str:
    payload = {"model": model, "messages": messages, "stream": False}
    with httpx.Client(timeout=120) as client:
        resp = client.post(OLLAMA_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {}).get("content", "")


def generate_reply(
    db: Session,
    chat_history: List[Dict[str, str]],
    user_message: str,
    model: str = DEFAULT_MODEL,
    allow_search: bool = True,
) -> str:
    memories = memory.recall_memory(db, user_message)
    rag_hits = query_rag(user_message)
    longterm = memory.auto_recall()
    context_blocks = []
    if longterm:
        context_blocks.append("Long-term memory:\n" + "\n".join(longterm))
    if memories:
        joined = "\n".join([m.text for m in memories])
        context_blocks.append(f"Relevant memories:\n{joined}")
    if rag_hits:
        rag_text = "\n---\n".join([f"{name}: {content}" for name, content, _ in rag_hits])
        context_blocks.append(f"Retrieved docs:\n{rag_text}")

    system = {"role": "system", "content": SYSTEM_RULES}
    augmented_history = [system]
    if context_blocks:
        augmented_history.append({"role": "system", "content": "\n\n".join(context_blocks)})
    augmented_history.extend(chat_history)
    augmented_history.append({"role": "user", "content": user_message})

    reply = _ollama_chat(augmented_history, model=model)
    reply = process_tools(db, reply, allow_search=allow_search)
    return reply
