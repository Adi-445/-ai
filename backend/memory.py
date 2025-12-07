from __future__ import annotations

import json
from datetime import datetime
from textwrap import shorten
from typing import List

from sqlalchemy.orm import Session

from . import models
from .db import LONGTERM_PATH


SUMMARY_INTERVAL = 10


def _load_longterm() -> List[dict]:
    try:
        return json.loads(LONGTERM_PATH.read_text(encoding="utf-8"))
    except Exception:
        LONGTERM_PATH.write_text("[]", encoding="utf-8")
        return []


def _write_longterm(data: List[dict]):
    LONGTERM_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_memory(db: Session, text: str) -> models.Memory:
    timestamp = datetime.utcnow().isoformat()
    entry = models.Memory(text=text, timestamp=timestamp)
    db.add(entry)
    db.commit()
    db.refresh(entry)

    data = _load_longterm()
    data.append({"text": text, "timestamp": timestamp})
    _write_longterm(data)
    return entry


def search_memory(db: Session, query: str, limit: int = 5) -> List[models.Memory]:
    return (
        db.query(models.Memory)
        .filter(models.Memory.text.ilike(f"%{query}%"))
        .order_by(models.Memory.id.desc())
        .limit(limit)
        .all()
    )


def delete_memory(db: Session, text: str):
    db.query(models.Memory).filter(models.Memory.text == text).delete()
    db.commit()
    data = _load_longterm()
    filtered = [item for item in data if item.get("text") != text]
    _write_longterm(filtered)


def recall_memory(db: Session, key: str) -> list[models.Memory]:
    return (
        db.query(models.Memory)
        .filter(models.Memory.text.ilike(f"%{key}%"))
        .order_by(models.Memory.id.desc())
        .all()
    )


def save_recall(db: Session, query: str, content: str) -> models.Recall:
    entry = models.Recall(query=query, content=content)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def save_search_cache(db: Session, query: str, results: str) -> models.SearchCache:
    entry = models.SearchCache(query=query, results=results)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_memories(db: Session) -> list[models.Memory]:
    return db.query(models.Memory).order_by(models.Memory.id.desc()).all()


def auto_recall() -> List[str]:
    data = _load_longterm()
    memories = []
    for item in data:
        if "text" in item:
            memories.append(f"[{item.get('timestamp', '')}] {item['text']}")
        elif "summary" in item:
            memories.append(f"[summary {item.get('timestamp', '')}] {item['summary']}")
    return memories


def autosummarize(db: Session):
    total_messages = db.query(models.Message).count()
    if total_messages == 0 or total_messages % SUMMARY_INTERVAL != 0:
        return

    all_memories = db.query(models.Memory).order_by(models.Memory.id.desc()).all()
    if not all_memories:
        return

    combined = " | ".join(m.text for m in all_memories)
    summary_text = shorten(combined, width=400, placeholder="...")

    timestamp = datetime.utcnow().isoformat()
    data = _load_longterm()
    data.append({"summary": summary_text, "timestamp": timestamp})
    _write_longterm(data)

    db.add(models.Memory(text=f"SUMMARY: {summary_text}", timestamp=timestamp))
    db.commit()
