from __future__ import annotations
import json
from pathlib import Path
from typing import List, Tuple

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - optional dependency
    SentenceTransformer = None

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "rag_data"
EMBED_PATH = DATA_DIR / "embeddings.json"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def _load_model():
    if SentenceTransformer is None:
        raise RuntimeError("sentence-transformers is required for embedding generation")
    return SentenceTransformer(MODEL_NAME)


def build_embeddings() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    documents = []
    for path in sorted(DATA_DIR.glob("*.txt")):
        documents.append((path.name, path.read_text(encoding="utf-8")))

    if not documents:
        sample = DATA_DIR / "welcome.txt"
        sample.write_text(
            "This folder holds documents used for retrieval augmented generation.\n"
            "Add more .txt files and rerun go.sh to refresh embeddings.",
            encoding="utf-8",
        )
        documents.append((sample.name, sample.read_text(encoding="utf-8")))

    model = _load_model()
    embeddings = model.encode([doc for _, doc in documents], convert_to_numpy=True).tolist()
    payload = {"documents": documents, "embeddings": embeddings}
    EMBED_PATH.write_text(json.dumps(payload), encoding="utf-8")


def load_embeddings():
    if not EMBED_PATH.exists():
        build_embeddings()
    data = json.loads(EMBED_PATH.read_text(encoding="utf-8"))
    docs = data.get("documents", [])
    embeds = np.array(data.get("embeddings", []))
    return docs, embeds


def query_rag(question: str, top_k: int = 3) -> List[Tuple[str, str, float]]:
    documents, embeddings = load_embeddings()
    if embeddings.size == 0:
        return []
    model = _load_model()
    query_vec = model.encode([question], convert_to_numpy=True)
    scores = cosine_similarity(query_vec, embeddings)[0]
    top_indices = np.argsort(scores)[::-1][:top_k]
    results = []
    for idx in top_indices:
        name, content = documents[idx]
        results.append((name, content, float(scores[idx])))
    return results
