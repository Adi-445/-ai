# Ollama Local Chat Platform

This project provides a FastAPI-based local chat interface for Ollama models with RAG, memory, and web search tooling.

## Quick start
```bash
# requires Python 3.10+, pipx, curl, and a local Ollama daemon
bash go.sh
```
The script will install `pipx` (if missing), provision `uv` through pipx, install dependencies directly into your system/user environment (no virtualenv), build RAG embeddings from `rag_data/*.txt`, initialize the SQLite database under `memory/memory.db`, and start the FastAPI server at `http://localhost:8000`.
`go.sh` defaults `PIP_EXTRA_INDEX_URL` to the CPU-only PyTorch wheel index to avoid pulling NVIDIA CUDA packages; unset or override this if you want CUDA-enabled wheels. Dependencies install system-wide, so make sure your user has permission to write to site-packages or run the script with appropriate privileges.

## Features
- WebSocket streaming chat with Ollama (defaults to `smollm2x`).
- SQLite storage for chats, messages, cross-chat memory, recall, and search cache.
- Retrieval Augmented Generation using documents in `rag_data/`.
- Automatic tool detection: `<web.search>query</web.search>` triggers DuckDuckGo search via `agent/search.sh`.
- Responsive web UI with markdown rendering, sidebar chat list, memory viewer, and settings.

## API endpoints
- `GET /api/new_chat` create and return a new chat id.
- `POST /api/chat` send a message and receive a full reply.
- `GET /api/history/{id}` fetch messages for a chat.
- `GET|POST /api/memory` list or add memory entries.
- `WebSocket /ws/chat` stream token responses.

## RAG embeddings
Edit or add `.txt` files in `rag_data/` then rerun `bash go.sh` (or `python -m backend.rag` with a `build_embeddings()` call) to refresh embeddings.

## Agent search
`agent/search.sh` uses DuckDuckGo HTML/JSON endpoints. `agent/main.py` wraps it for backend calls.

## Notes
- Ensure Ollama is running locally with the `smollm2x` model pulled.
- Logging writes to `logs/app.log` with rotation.
