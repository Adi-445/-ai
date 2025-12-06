from sqlalchemy.orm import Session
from . import models


def save_memory(db: Session, key: str, content: str) -> models.Memory:
    entry = models.Memory(key=key, content=content)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def recall_memory(db: Session, key: str) -> list[models.Memory]:
    return (
        db.query(models.Memory)
        .filter(models.Memory.key.ilike(f"%{key}%"))
        .order_by(models.Memory.created_at.desc())
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
    return db.query(models.Memory).order_by(models.Memory.created_at.desc()).all()
